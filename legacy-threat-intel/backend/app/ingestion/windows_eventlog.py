"""Windows Event Log collection (live authorized host or exported XML).

Live collection uses the built-in ``wevtutil.exe`` and requires an explicitly
authorized Windows host. The XML variant reads an operator-exported file and
works from Linux/Docker containers. No credentials are read from source code.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ingestion.base import IngestionSource
from app.schemas import NormalizedEvent
from app.utils import make_id, parse_ts, redact, utcnow

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

EVENT_TYPE_MAP: dict[int, tuple[str, str, str]] = {
    1102: ("audit_cleared", "audit_log_cleared", "Audit log was cleared"),
    4624: ("auth_success", "logon", "Successful account logon"),
    4625: ("auth_failure", "logon", "Failed account logon"),
    4634: ("auth_logout", "logoff", "Account logoff"),
    4647: ("auth_logout", "logoff", "User initiated logoff"),
    4672: ("privilege_assigned", "privilege", "Special privileges assigned to logon"),
    4688: ("process_creation", "process", "New process created"),
    4697: ("service_installed", "service", "Service installed"),
    4720: ("account_change", "account_created", "User account created"),
    4722: ("account_change", "account_enabled", "User account enabled"),
    4723: ("account_change", "password_change", "Password change attempted"),
    4724: ("account_change", "password_reset", "Password reset attempted"),
    4732: ("account_change", "group_member_added", "Member added to security group"),
    4735: ("account_change", "group_changed", "Security-enabled group changed"),
    4737: ("account_change", "group_changed", "Security-enabled group changed"),
    4758: ("account_change", "group_changed", "Security-disabled group changed"),
    4767: ("account_change", "account_unlocked", "User account unlocked"),
    7045: ("service_installed", "service", "Service installed in System log"),
    4103: ("powershell_script", "powershell", "PowerShell module logging"),
    4104: ("powershell_script", "powershell", "PowerShell script block logging"),
}

_NULL_IPS = {"", "-", "0.0.0.0", "::", "::1", "127.0.0.1", "n/a", "unknown"}


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_win_time(value: str) -> datetime:
    """Normalize 100ns Windows timestamps to Python microseconds."""
    def trim(match: re.Match[str]) -> str:
        return "." + (match.group(1) + "000000")[:6] + "Z"

    normalized = re.sub(r"\.(\d{1,9})Z$", trim, value.strip())
    try:
        return parse_ts(normalized)
    except ValueError:
        return utcnow()


class WindowsXmlParser:
    """Converts Windows event XML into normalized security events."""

    def __init__(self, source_name: str, allowed_ids: set[int]):
        self.source_name = source_name
        self.allowed_ids = allowed_ids

    def parse(self, xml_text: str) -> list[NormalizedEvent]:
        text = (xml_text or "").strip()
        if not text:
            return []
        candidates = [text]
        if not text.startswith("<?xml") and "<Events" not in text[:200]:
            candidates.insert(0, f"<Events>{text}</Events>")
        root = None
        for candidate in candidates:
            try:
                root = ET.fromstring(candidate)
                break
            except ET.ParseError:
                continue
        if root is None:
            raise ValueError("Windows Event Log XML could not be parsed")
        events: list[NormalizedEvent] = []
        for element in root.iter():
            if _localname(element.tag) != "Event":
                continue
            event = self._parse_one(element)
            if event:
                events.append(event)
        return events

    def _parse_one(self, element: ET.Element) -> NormalizedEvent | None:
        system: dict[str, Any] = {}
        data: dict[str, str] = {}
        for child in element:
            name = _localname(child.tag)
            if name == "System":
                for node in child:
                    node_name = _localname(node.tag)
                    system[node_name] = node.text or ""
                    if node_name == "Provider":
                        system["ProviderName"] = node.attrib.get("Name", "")
                    if node_name == "TimeCreated":
                        system["SystemTime"] = node.attrib.get("SystemTime", "")
            elif name in {"EventData", "UserData"}:
                for node in child.iter():
                    if _localname(node.tag) == "Data":
                        key = node.attrib.get("Name") or node.attrib.get("name")
                        if key:
                            data[key] = (node.text or "")[:4000]

        try:
            event_id = int(system.get("EventID", "0"))
        except (TypeError, ValueError):
            return None
        if self.allowed_ids and event_id not in self.allowed_ids:
            return None
        event_type, action, default_message = EVENT_TYPE_MAP.get(
            event_id, ("windows_event", f"event_{event_id}", "Windows security event")
        )

        source_ip = (data.get("IpAddress") or data.get("SourceIp") or data.get("SourceAddress") or "").strip()
        source_ip = None if source_ip.lower() in _NULL_IPS else source_ip[:64]
        dest_ip = (data.get("DestAddress") or data.get("DestinationIp") or "").strip()
        dest_ip = None if dest_ip.lower() in _NULL_IPS else dest_ip[:64]
        workstation = (data.get("WorkstationName") or "").strip() or None
        user = (data.get("TargetUserName") or data.get("SubjectUserName") or "").strip() or None
        domain = (data.get("TargetDomainName") or data.get("SubjectDomainName") or "").strip() or None
        command_line = data.get("CommandLine") or data.get("ScriptBlockText") or ""
        process = (data.get("NewProcessName") or data.get("ProcessName") or "").strip() or None
        channel = system.get("Channel", "")
        computer = system.get("Computer", "")
        record_id = system.get("EventRecordID", "")
        timestamp = _parse_win_time(system.get("SystemTime", ""))
        raw_payload = " ".join(f"{k}={v}" for k, v in list(data.items())[:40])

        tags = [f"windows_event_id:{event_id}"]
        if channel:
            tags.append(f"channel:{channel}")
        if event_id in {4672, 4688, 4697, 7045, 4104, 1102}:
            tags.append("high_value_windows_event")

        indicators: list[dict[str, str]] = []
        if source_ip:
            indicators.append({"type": "ip", "value": source_ip})
        if dest_ip:
            indicators.append({"type": "ip", "value": dest_ip})

        return NormalizedEvent(
            event_id=make_id("evt", self.source_name, channel, record_id or raw_payload[:200]),
            source_type="windows_eventlog",
            source_name=self.source_name,
            source_id=f"{computer}/{channel}/{record_id}",
            host=computer[:256],
            event_type=event_type,
            event_action=action,
            timestamp=timestamp,
            actor_user=user,
            actor_domain=domain,
            source_ip=source_ip,
            destination_ip=dest_ip,
            process_name=process,
            command_line=redact(command_line, 2000) or None,
            message=redact(data.get("Message") or default_message, 1000),
            raw=redact(raw_payload, 4000),
            tags=tags,
            indicators=indicators,
            asset_id=computer[:256] or None,
            dedupe_key=make_id("evt", self.source_name, channel, record_id or timestamp.isoformat()),
            metadata={
                "event_id": event_id,
                "channel": channel,
                "record_id": record_id,
                "provider": system.get("ProviderName", ""),
                "logon_type": data.get("LogonType"),
                "status_code": data.get("Status"),
                "sub_status": data.get("SubStatus"),
                "workstation": workstation,
                "level": system.get("Level"),
            },
        )


class WindowsEventLogSource(IngestionSource):
    name = "windows_eventlog"
    source_type = "windows_eventlog"

    def __init__(self, settings: "Settings"):
        super().__init__(settings)
        self.allowed_ids = set(settings.windows_eventlog_event_ids)
        self.parser = WindowsXmlParser(self.name, self.allowed_ids)

    def check_available(self) -> tuple[bool, str]:
        if not self.settings.windows_eventlog_enabled:
            return False, "WINDOWS_EVENTLOG_ENABLED=false"
        if sys.platform != "win32":
            return False, "Live Windows Event Log requires a Windows host (use WINDOWS_EVENTLOG_XML_PATH in Docker)"
        if not shutil.which("wevtutil.exe"):
            return False, "wevtutil.exe not found on PATH"
        return True, "wevtutil available on authorized Windows host"

    def collect(self, since: datetime | None = None) -> list[NormalizedEvent]:
        available, reason = self.check_available()
        if not available:
            raise RuntimeError(reason)
        lower_bound = since or (utcnow() - timedelta(minutes=self.settings.windows_eventlog_lookback_minutes))
        since_text = lower_bound.strftime("%Y-%m-%dT%H:%M:%S")
        collected: list[NormalizedEvent] = []
        for channel in self.settings.windows_eventlog_channels:
            query = f"*[System[TimeCreated[@SystemTime>='{since_text}']]]"
            command = [
                "wevtutil", "qe", channel,
                f"/q:{query}",
                "/f:xml",
                f"/c:{self.settings.windows_eventlog_max_events}",
                "/rd:true",
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                    shell=False,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RuntimeError(f"wevtutil failed for {channel}: {exc}") from exc
            if completed.returncode != 0:
                raise RuntimeError(f"wevtutil error for {channel}: {redact(completed.stderr, 500)}")
            collected.extend(self.parser.parse(completed.stdout))
        self.logger.info("collected=%s channels=%s", len(collected), len(self.settings.windows_eventlog_channels))
        return collected


class WindowsEventLogFileSource(IngestionSource):
    """Reads an operator-exported Windows Event Log XML file."""

    name = "windows_eventlog_file"
    source_type = "windows_eventlog"

    def __init__(self, settings: "Settings"):
        super().__init__(settings)
        self.allowed_ids = set(settings.windows_eventlog_event_ids)
        self.parser = WindowsXmlParser(self.name, self.allowed_ids)

    def _path(self) -> Path | None:
        raw = (self.settings.windows_eventlog_xml_path or "").strip()
        return Path(raw) if raw else None

    def check_available(self) -> tuple[bool, str]:
        path = self._path()
        if path is None:
            return False, "WINDOWS_EVENTLOG_XML_PATH is not configured"
        if not path.is_file():
            return False, f"exported XML file not found: {path}"
        if not path.stat().st_size:
            return False, "exported XML file is empty"
        return True, "exported Windows Event Log XML available"

    def collect(self, since: datetime | None = None) -> list[NormalizedEvent]:
        available, reason = self.check_available()
        if not available:
            raise RuntimeError(reason)
        assert self._path() is not None
        text = self._path().read_text(encoding="utf-8", errors="replace")
        events = self.parser.parse(text)
        if since:
            events = [event for event in events if event.timestamp >= since]
        self.logger.info("collected=%s from=%s", len(events), self._path())
        return events
