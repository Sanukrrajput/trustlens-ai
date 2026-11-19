"""SSRF-resistant HTTP fetching for untrusted URLs.

The fetcher never hands an attacker-controlled URL to requests/urllib directly.
It validates scheme, credentials, port and every DNS answer, pins the TCP
connection to a validated IP (while keeping the original Host header and TLS
SNI), handles redirects manually and streams the response with a hard byte cap.
All failures are returned as structured data; no raw exception escapes.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.intelligence import dedupe, is_public_ip, iso, setting

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "application/json",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
        "text/csv",
    }
)
BLOCKED_MIME_MARKERS = (
    "executable",
    "x-msdownload",
    "octet-stream",
    "zip",
    "rar",
    "tar",
    "gzip",
    "x-7z",
    "java-archive",
    "x-shockwave-flash",
    "msword",
    "vnd.microsoft",
    "pdf",
)
HEADER_WHITELIST = (
    "content-type",
    "content-length",
    "server",
    "last-modified",
    "location",
    "content-encoding",
    "cache-control",
    "strict-transport-security",
    "x-frame-options",
)
HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.\-]*[a-z0-9])?$")
BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".localdomain", ".home.arpa")


class UnsafeURLError(ValueError):
    """Raised internally when a URL or DNS answer fails validation."""


def _socket_address(ip: str, port: int) -> tuple[int, Any]:
    """Return (address_family, sockaddr) suitable for socket.connect()."""
    address = ipaddress.ip_address(ip.split("%", 1)[0])
    if address.version == 6:
        return socket.AF_INET6, (ip, port, 0, 0)
    return socket.AF_INET, (ip, port)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection whose socket is connected to a pre-validated IP."""

    def __init__(self, host: str, port: int | None = None, *, pinned_ip: str, timeout: float | None = None, **kwargs: Any) -> None:
        super().__init__(host, port, timeout=timeout, **kwargs)
        self.pinned_ip = pinned_ip

    def connect(self) -> None:  # noqa: D102 - documented by base class
        family, sockaddr = _socket_address(self.pinned_ip, self.port)
        sock = socket.socket(family, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(sockaddr)
        self.sock = sock


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection pinned to an IP but with SNI/Host for the real name."""

    def __init__(
        self,
        host: str,
        port: int | None = None,
        *,
        pinned_ip: str,
        timeout: float | None = None,
        context: ssl.SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=context, **kwargs)
        self.pinned_ip = pinned_ip

    def connect(self) -> None:
        family, sockaddr = _socket_address(self.pinned_ip, self.port)
        sock = socket.socket(family, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(sockaddr)
        context = self._context or ssl.create_default_context()
        # server_hostname deliberately uses the original DNS name, not the IP.
        self.sock = context.wrap_socket(sock, server_hostname=self.host)


class SafeURLFetcher:
    """Fetch text content from a URL with SSRF defences."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.max_bytes = max(1024, int(setting(settings, "max_fetch_bytes", 262_144)))
        self.timeout = max(0.1, float(setting(settings, "fetch_timeout_seconds", 8.0)))
        self.max_redirects = max(0, min(10, int(setting(settings, "max_redirects", 4))))
        self.allowed_ports = self._configure_ports(settings)

    @staticmethod
    def _configure_ports(settings: Any) -> frozenset[int]:
        raw = getattr(settings, "allowed_fetch_ports", None) or getattr(settings, "allowed_ports", None)
        if raw:
            try:
                ports = frozenset(int(port) for port in raw)
                if ports:
                    return ports
            except (TypeError, ValueError):
                pass
        return frozenset({80, 443})

    def _validate_url(self, url: Any) -> tuple[Any, str, int]:
        """Return (parsed_url, hostname, port) or raise UnsafeURLError."""
        if not isinstance(url, str) or not url.strip():
            raise UnsafeURLError("empty URL")
        try:
            parts = urlsplit(url.strip())
        except ValueError as exc:
            raise UnsafeURLError(f"malformed URL: {exc}") from exc
        scheme = (parts.scheme or "").lower()
        if scheme not in {"http", "https"}:
            raise UnsafeURLError(f"unsupported URL scheme: {scheme or '(none)'}")
        if parts.username or parts.password:
            raise UnsafeURLError("URL credentials/userinfo are not allowed")
        try:
            host = (parts.hostname or "").strip().lower().rstrip(".")
        except ValueError as exc:
            raise UnsafeURLError(f"invalid hostname: {exc}") from exc
        if not host or len(host) > 253 or not HOSTNAME_RE.match(host):
            raise UnsafeURLError(f"invalid or non-ASCII hostname: {host!r}")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(BLOCKED_HOST_SUFFIXES):
            raise UnsafeURLError(f"local/internal hostname is not allowed: {host}")
        if host.startswith("metadata"):
            raise UnsafeURLError(f"cloud metadata hostname is not allowed: {host}")
        try:
            port = parts.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise UnsafeURLError(f"invalid port: {exc}") from exc
        if port not in self.allowed_ports:
            raise UnsafeURLError(f"port {port} is not in the allowed port list")

        # Numeric aliases such as 2130706433 or 0x7f000001 can be resolved as
        # loopback by some resolvers. Reject them rather than relying on libc.
        if re.fullmatch(r"[0-9.]+", host) or re.fullmatch(r"0[xX][0-9a-fA-F]+", host):
            raise UnsafeURLError(f"ambiguous numeric hostname is not allowed: {host}")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None and not is_public_ip(literal):
            raise UnsafeURLError(f"non-public IP literal is not allowed: {host}")
        return parts, host, port

    def _resolve(self, host: str, port: int) -> list[str]:
        """Resolve and validate *every* answer to prevent DNS rebinding."""
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except Exception as exc:
            raise UnsafeURLError(f"DNS resolution failed for {host}: {type(exc).__name__}: {exc}") from exc
        if not infos:
            raise UnsafeURLError(f"DNS resolution returned no addresses for {host}")
        addresses: list[str] = []
        for info in infos:
            try:
                candidate = str(info[4][0])
            except (IndexError, TypeError):
                raise UnsafeURLError(f"malformed DNS answer for {host}")
            if not is_public_ip(candidate):
                raise UnsafeURLError(f"DNS answer for {host} is non-public: {candidate}")
            addresses.append(candidate)
        return dedupe(addresses)

    def _open_connection(self, scheme: str, host: str, port: int, pinned_ip: str) -> Any:
        if scheme == "https":
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            return _PinnedHTTPSConnection(
                host,
                port,
                pinned_ip=pinned_ip,
                timeout=self.timeout,
                context=context,
            )
        return _PinnedHTTPConnection(host, port, pinned_ip=pinned_ip, timeout=self.timeout)

    @staticmethod
    def _certificate(connection: Any) -> dict[str, Any] | None:
        sock = getattr(connection, "sock", None)
        getter = getattr(sock, "getpeercert", None)
        if not getter:
            return None
        try:
            certificate = getter()
        except Exception:
            return None
        if not certificate:
            return None

        def flatten(field: str) -> str:
            parts: list[str] = []
            for rdn in certificate.get(field, ()):
                for key, value in rdn:
                    parts.append(f"{key}={value}")
            return ", ".join(parts)

        san = [value for key, value in certificate.get("subjectAltName", ()) if key in {"DNS", "IP Address"}]
        return {
            "subject": flatten("subject"),
            "issuer": flatten("issuer"),
            "not_before": certificate.get("notBefore"),
            "not_after": certificate.get("notAfter"),
            "san": san[:25],
            "serial_number": certificate.get("serialNumber"),
            "observed_at": iso(),
        }

    def _read_body(self, response: Any) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        total = 0
        truncated = False
        while True:
            chunk = response.read(min(8192, self.max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total >= self.max_bytes:
                truncated = True
                break
        return b"".join(chunks)[: self.max_bytes], truncated

    @staticmethod
    def _decode(body: bytes, content_type: str | None) -> str:
        charset = "utf-8"
        if content_type:
            match = re.search(r"charset\s*=\s*[\"']?([\w\-]+)", content_type, re.I)
            if match:
                charset = match.group(1)
        try:
            return body.decode(charset, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")

    @staticmethod
    def _error_result(url: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": status,
            "url": url,
            "final_url": extra.pop("final_url", url),
            "redirect_chain": extra.pop("redirect_chain", []),
            "http_status": None,
            "content_type": None,
            "body_preview": "",
            "headers_subset": {},
            "certificate": None,
            "limitations": [],
            "errors": [message],
            "truncated": False,
        }
        result.update(extra)
        return result

    def fetch(self, url: str) -> dict[str, Any]:
        """Fetch a URL safely; always returns a structured result dict."""
        chain: list[str] = []
        current = url
        try:
            for hop in range(self.max_redirects + 1):
                try:
                    parts, host, port = self._validate_url(current)
                except UnsafeURLError as exc:
                    return self._error_result(url, "blocked", str(exc), final_url=current, redirect_chain=list(chain))

                try:
                    addresses = self._resolve(host, port)
                except UnsafeURLError as exc:
                    return self._error_result(url, "blocked", str(exc), final_url=current, redirect_chain=list(chain))

                connection: Any = None
                try:
                    connection = self._open_connection(parts.scheme, host, port, addresses[0])
                    path = parts.path or "/"
                    if parts.query:
                        path = f"{path}?{parts.query}"
                    host_header = host if port in {80, 443} else f"{host}:{port}"
                    connection.request(
                        "GET",
                        path,
                        headers={
                            "Host": host_header,
                            "Accept": "text/html, text/plain, application/json;q=0.9",
                            "User-Agent": "HireShieldAI-SafetyScanner/1.0 (+text-only)",
                            "Connection": "close",
                        },
                    )
                    response = connection.getresponse()
                    http_status = int(getattr(response, "status", 0) or 0)
                    raw_headers = response.getheaders()
                    headers = {str(key).lower(): str(value) for key, value in raw_headers}
                    content_type = headers.get("content-type")
                    certificate = self._certificate(connection)
                    subset = {key: headers[key] for key in HEADER_WHITELIST if key in headers}

                    if http_status in REDIRECT_STATUSES and headers.get("location"):
                        if hop >= self.max_redirects:
                            return self._error_result(
                                url,
                                "blocked",
                                f"redirect limit ({self.max_redirects}) exceeded",
                                final_url=current,
                                redirect_chain=list(chain),
                                http_status=http_status,
                                content_type=content_type,
                                headers_subset=subset,
                                certificate=certificate,
                            )
                        next_url = urljoin(current, headers["location"].strip())
                        chain.append(next_url)
                        current = next_url
                        continue

                    result: dict[str, Any] = {
                        "status": "ok",
                        "url": url,
                        "final_url": current,
                        "redirect_chain": list(chain),
                        "http_status": http_status,
                        "content_type": content_type,
                        "body_preview": "",
                        "headers_subset": subset,
                        "certificate": certificate,
                        "limitations": [],
                        "errors": [],
                        "truncated": False,
                    }
                    if http_status < 200 or http_status >= 300:
                        result["status"] = "error"
                        result["errors"].append(f"HTTP {http_status} returned by {current}")
                        return result

                    if not content_type:
                        result["status"] = "blocked"
                        result["errors"].append("missing Content-Type header; binary content cannot be excluded")
                        return result
                    mime = content_type.split(";", 1)[0].strip().lower()
                    if mime not in ALLOWED_CONTENT_TYPES or any(marker in mime for marker in BLOCKED_MIME_MARKERS):
                        result["status"] = "blocked"
                        result["errors"].append(f"content type not allowed for text-only scanning: {mime}")
                        result["limitations"].append("Binary downloads and executables are never fetched.")
                        return result

                    body, truncated = self._read_body(response)
                    if truncated:
                        result["limitations"].append(
                            f"Response body truncated at the {self.max_bytes} byte safety limit."
                        )
                    result["truncated"] = truncated
                    result["body_preview"] = self._decode(body, content_type)[:6000]
                    result["bytes_read"] = len(body)
                    result["observed_at"] = iso()
                    return result
                except Exception as exc:
                    return self._error_result(
                        url,
                        "error",
                        f"{type(exc).__name__}: {exc}",
                        final_url=current,
                        redirect_chain=list(chain),
                    )
                finally:
                    if connection is not None:
                        try:
                            connection.close()
                        except Exception:
                            pass
            return self._error_result(url, "blocked", "redirect loop detected", final_url=current, redirect_chain=list(chain))
        except Exception as exc:  # last-resort guard: never leak raw exceptions
            return self._error_result(url, "error", f"{type(exc).__name__}: {exc}", redirect_chain=list(chain))

    def probe_tls(self, host: str, port: int = 443) -> dict[str, Any]:
        """Perform a pinned TLS handshake and return certificate metadata only."""
        target = f"https://{host}:{port}/" if port != 443 else f"https://{host}/"
        connection: Any = None
        try:
            _parts, validated_host, validated_port = self._validate_url(target)
            addresses = self._resolve(validated_host, validated_port)
            connection = self._open_connection("https", validated_host, validated_port, addresses[0])
            connection.connect()
            return {
                "status": "ok",
                "host": validated_host,
                "certificate": self._certificate(connection),
                "limitations": ["Certificate chain trust is validated by the system trust store."],
                "errors": [],
                "observed_at": iso(),
            }
        except UnsafeURLError as exc:
            return {
                "status": "blocked",
                "host": host,
                "certificate": None,
                "limitations": [],
                "errors": [str(exc)],
                "observed_at": iso(),
            }
        except Exception as exc:
            return {
                "status": "error",
                "host": host,
                "certificate": None,
                "limitations": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
                "observed_at": iso(),
            }
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


__all__ = ["SafeURLFetcher", "UnsafeURLError"]
