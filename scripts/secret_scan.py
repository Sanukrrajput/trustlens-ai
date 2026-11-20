"""Fail-closed secret-hygiene check for tracked repository files.

This is a fast pre-commit/CI guard, not a replacement for a dedicated entropy
scanner. It checks that secret-bearing environment files are not tracked and
looks for well-known credential prefixes and private-key blocks in tracked text
files. Example templates and obvious placeholders are allowed.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SKIP_NAMES = {"secret_scan.py"}
SKIP_SUFFIXES = {".joblib", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".csv", ".zip", ".gz"}
MAX_BYTES = 2_000_000
PLACEHOLDER_TOKENS = (
    "example", "changeme", "your_", "placeholder", "replace", "dummy", "fake",
    "configured", "sample", "<", "${", "xxx", "todo", "test_key", "not_a_key",
    "development-only", "before-launch",
)

# (label, pattern). Patterns intentionally require a substantial value after
# the prefix so that documentation examples do not trigger them.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_key", re.compile(r"\bsk-(?:live-)?[A-Za-z0-9]{20,}\b")),
    ("razorpay_live_key", re.compile(r"\brzp_live_[A-Za-z0-9]{10,}\b")),
    ("stripe_live_key", re.compile(r"\bsk_live_[A-Za-z0-9]{10,}\b")),
    ("webhook_secret", re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(?:secret_key|api_key|webhook_secret|password)\s*=\s*[\"']?"
            r"([A-Za-z0-9_\-+/=]{16,})(?![\w(])"
        ),
    ),
)


def tracked_files() -> list[str]:
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="replace")
        return [item for item in output.split("\0") if item]
    except (OSError, subprocess.CalledProcessError):
        return []


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in PLACEHOLDER_TOKENS)


def scan_text(relpath: str, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(1) if match.groups() else match.group(0)
            if is_placeholder(value):
                continue
            findings.append(
                {"file": relpath, "line": line_number, "kind": label}
            )
    return findings


def scan(files: Iterable[str]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    for relpath in files:
        path = ROOT / relpath
        if not path.is_file() or path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        findings.extend(scan_text(relpath, text))

    tracked = set(tracked_files())
    forbidden = sorted(
        item for item in tracked
        if Path(item).name.startswith(".env") and Path(item).name != ".env.example"
    )
    backups = sorted(item for item in tracked if item.startswith("backups/"))
    return {
        "status": "fail" if findings or forbidden or backups else "ok",
        "scanned_files": scanned,
        "findings": findings,
        "tracked_env_files": forbidden,
        "tracked_backups": backups,
    }


def main() -> int:
    result = scan(tracked_files())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
