"""Domain intelligence: RDAP, DNS, TLS and optional commercial threat feeds.

Every finding is wrapped with provenance. External feeds are optional and
report ``not_configured`` rather than inventing a clean bill of health.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from dns import resolver as dns_resolver
from dns.exception import DNSException

from app.intelligence import (
    BRAND_NAMES,
    fact,
    homoglyph_normalise,
    iso,
    levenshtein,
    make_indicator,
    registrable_domain,
    setting,
    utcnow,
)
from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher

DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT")


def _section(
    status: str,
    source: str,
    limitations: list[str] | None = None,
    *,
    confidence: float = 0.7,
    independently_verified: bool = False,
    **values: Any,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "status": status,
        "source": source,
        "observed_at": iso(),
        "confidence": confidence,
        "independently_verified": independently_verified,
        "limitations": list(limitations or []),
    }
    section.update(values)
    return section


def _not_configured(name: str, explanation: str) -> dict[str, Any]:
    return _section(
        "not_configured",
        name,
        [explanation],
        confidence=0.0,
        data={},
    )


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        collapsed = re.sub(r"\s+", " ", str(value or "")).strip()
        try:
            parsed = datetime.strptime(collapsed, "%b %d %H:%M:%S %Y %Z")
        except (TypeError, ValueError):
            try:
                parsed = datetime.strptime(collapsed, "%b %d %H:%M:%S %Y GMT").replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _vcard_values(entity: dict[str, Any], key: str) -> list[str]:
    results: list[str] = []
    vcard_array = entity.get("vcardArray")
    if isinstance(vcard_array, list) and len(vcard_array) > 1:
        for prop in vcard_array[1]:
            if isinstance(prop, list) and len(prop) >= 4 and str(prop[0]).lower() == key:
                value = prop[3]
                if isinstance(value, str) and value.strip():
                    results.append(value.strip())
    for prop in entity.get("vcard") or []:
        if isinstance(prop, dict) and str(prop.get("name", "")).lower() == key:
            value = prop.get("value")
            if isinstance(value, str) and value.strip():
                results.append(value.strip())
    return results


class DomainAnalyser:
    """Collect domain facts with explicit provenance and limitations."""

    def __init__(self, settings: Any, repos: Any = None) -> None:
        self.settings = settings
        self.repos = repos
        self.timeout = max(0.5, float(setting(settings, "fetch_timeout_seconds", 8.0)))
        self.fetcher = SafeURLFetcher(settings)

    # ------------------------------------------------------------------ RDAP
    def _rdap(self, domain: str) -> dict[str, Any]:
        if not bool(setting(self.settings, "rdap_enabled", True)):
            return _section("disabled", "rdap.org", ["RDAP lookups are disabled in settings."], data={})
        source = "https://rdap.org/domain/"
        url = f"{source}{quote(domain, safe='.-')}"
        try:
            response = requests.get(url, timeout=self.timeout, headers={"Accept": "application/rdap+json"})
            if response.status_code != 200:
                return _section(
                    "error",
                    url,
                    [f"RDAP returned HTTP {response.status_code}."],
                    data={},
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("RDAP response was not a JSON object")
        except Exception as exc:
            return _section(
                "error",
                url,
                [f"RDAP lookup failed: {type(exc).__name__}: {exc}"],
                data={},
            )

        values: dict[str, Any] = {}
        for event in payload.get("events") or []:
            action = str(event.get("eventAction", "")).lower()
            if action in {"registration", "registered"} and "registration_date" not in values:
                values["registration_date"] = fact(
                    event.get("eventDate"), source=url, confidence=0.85, limitations=["RDAP event dates are registrar-reported."]
                )
            elif action in {"expiration", "expiry", "expiration_date"} and "expiration_date" not in values:
                values["expiration_date"] = fact(event.get("eventDate"), source=url, confidence=0.85)

        registrar: str | None = None
        abuse_contact: str | None = None
        for entity in payload.get("entities") or []:
            if not isinstance(entity, dict):
                continue
            roles = {str(role).lower() for role in entity.get("roles") or []}
            names = _vcard_values(entity, "fn")
            emails = [value.removeprefix("mailto:") for value in _vcard_values(entity, "email")]
            if "registrar" in roles and registrar is None:
                registrar = names[0] if names else (entity.get("handle") or None)
            if "abuse" in roles and abuse_contact is None:
                abuse_contact = emails[0] if emails else (entity.get("handle") or None)
        values["registrar"] = fact(registrar, source=url, confidence=0.8)
        values["abuse_contact"] = fact(
            abuse_contact,
            source=url,
            confidence=0.7,
            limitations=["Only publicly published abuse contacts are returned; no private WHOIS data is used."],
        )
        statuses = [str(item) for item in payload.get("status") or [] if item]
        values["statuses"] = fact(statuses, source=url, confidence=0.75)
        nameservers = [
            str(item.get("ldhName") or item.get("unicodeName"))
            for item in payload.get("nameservers") or []
            if isinstance(item, dict) and (item.get("ldhName") or item.get("unicodeName"))
        ]
        values["nameservers"] = fact(nameservers, source=url, confidence=0.8)

        return _section(
            "ok" if values else "unavailable",
            url,
            ["Registrant identity is commonly redacted; absence is not evidence of fraud."],
            confidence=0.8,
            reference_url=url,
            data=values,
        )

    # ------------------------------------------------------------------- DNS
    def _dns(self, host: str) -> dict[str, Any]:
        if not bool(setting(self.settings, "dns_enabled", True)):
            return _section("disabled", "dnspython", ["DNS lookups are disabled in settings."], data={})
        resolver = dns_resolver.Resolver()
        resolver.timeout = self.timeout
        resolver.lifetime = self.timeout
        data: dict[str, Any] = {}
        limitations: list[str] = ["DNSSEC validation is not performed by this scanner."]
        failures = 0
        for record_type in DNS_TYPES:
            try:
                answer = resolver.resolve(host, record_type)
                values: list[str] = []
                for record in answer:
                    if record_type == "MX":
                        values.append(f"{record.exchange} (preference={record.preference})")
                    else:
                        values.append(str(record))
                data[record_type.lower()] = fact(
                    values, source="authoritative DNS answer via dnspython", confidence=0.85
                )
            except DNSException as exc:
                failures += 1
                data[record_type.lower()] = fact(
                    [], source="authoritative DNS answer via dnspython", confidence=0.5, limitations=[type(exc).__name__]
                )
            except Exception as exc:
                failures += 1
                data[record_type.lower()] = fact(
                    [], source="DNS", confidence=0.2, limitations=[f"{type(exc).__name__}: {exc}"]
                )
        status = "ok" if failures < len(DNS_TYPES) else "unavailable"
        return _section(status, "dnspython", limitations, confidence=0.8, data=data)

    # ------------------------------------------------------------------- TLS
    @staticmethod
    def _hostname_matches(hostname: str, san: list[str]) -> bool | None:
        if not san:
            return None
        name = hostname.lower().rstrip(".")
        for entry in san:
            candidate = str(entry).lower().rstrip(".")
            if candidate == name:
                return True
            if candidate.startswith("*.") and name.endswith(candidate[1:]):
                return True
        return False

    def _tls(self, host: str) -> dict[str, Any]:
        if not bool(setting(self.settings, "tls_enabled", True)):
            return _section("disabled", "TLS probe", ["TLS lookups are disabled in settings."], data={})
        probe = self.fetcher.probe_tls(host)
        certificate = probe.get("certificate")
        if not certificate:
            return _section(
                probe.get("status", "error"),
                "pinned TLS connection",
                list(probe.get("limitations") or []) + list(probe.get("errors") or []),
                confidence=0.3,
                data={"certificate": fact(None, source="pinned TLS connection", confidence=0.3)},
            )
        not_before = _parse_date(certificate.get("not_before"))
        not_after = _parse_date(certificate.get("not_after"))
        now = utcnow()
        days_to_expiry = int((not_after - now).total_seconds() // 86400) if not_after else None
        hostname_match = self._hostname_matches(host, list(certificate.get("san") or []))
        valid = bool(
            (not_before is None or not_before <= now) and (not_after is None or not_after >= now) and hostname_match is not False
        )
        data = {
            "subject": fact(certificate.get("subject"), source="X.509 certificate", confidence=0.95),
            "issuer": fact(certificate.get("issuer"), source="X.509 certificate", confidence=0.95),
            "not_before": fact(certificate.get("not_before"), source="X.509 certificate", confidence=0.95),
            "not_after": fact(certificate.get("not_after"), source="X.509 certificate", confidence=0.95),
            "san": fact(certificate.get("san") or [], source="X.509 certificate", confidence=0.95),
            "days_to_expiry": fact(days_to_expiry, source="X.509 certificate", confidence=0.9),
            "hostname_match": fact(hostname_match, source="X.509 certificate / hostname check", confidence=0.9),
            "valid": fact(valid, source="X.509 certificate / hostname check", confidence=0.9),
        }
        return _section(
            "ok",
            "pinned TLS connection",
            ["Certificate validity is a technical check, not proof that the site is legitimate."],
            confidence=0.9,
            data=data,
        )

    # ----------------------------------------------------------- Threat feeds
    def _virustotal(self, domain: str) -> dict[str, Any]:
        key = str(setting(self.settings, "virustotal_api_key", "") or "").strip()
        if not key:
            return _not_configured("VirusTotal v3", "VIRUSTOTAL_API_KEY is not configured; no reputation data was requested.")
        url = f"https://www.virustotal.com/api/v3/domains/{quote(domain, safe='.-')}"
        try:
            response = requests.get(url, headers={"x-apikey": key}, timeout=self.timeout)
            if response.status_code != 200:
                return _section("error", url, [f"VirusTotal returned HTTP {response.status_code}."], data={})
            attributes = (response.json().get("data") or {}).get("attributes") or {}
            stats = attributes.get("last_analysis_stats") or {}
            data = {
                "malicious": fact(int(stats.get("malicious", 0)), source=url, confidence=0.8),
                "suspicious": fact(int(stats.get("suspicious", 0)), source=url, confidence=0.8),
                "harmless": fact(int(stats.get("harmless", 0)), source=url, confidence=0.8),
                "undetected": fact(int(stats.get("undetected", 0)), source=url, confidence=0.8),
                "reputation": fact(attributes.get("reputation"), source=url, confidence=0.7),
            }
            return _section(
                "ok",
                url,
                ["Third-party engine verdicts can disagree; they are indicators, not ground truth."],
                confidence=0.8,
                reference_url=f"https://www.virustotal.com/gui/domain/{domain}",
                data=data,
            )
        except Exception as exc:
            return _section("error", url, [f"VirusTotal lookup failed: {type(exc).__name__}: {exc}"], data={})

    def _safe_browsing(self, domain: str) -> dict[str, Any]:
        key = str(setting(self.settings, "google_safebrowsing_api_key", "") or "").strip()
        if not key:
            return _not_configured(
                "Google Safe Browsing v4",
                "GOOGLE_SAFEBROWSING_API_KEY is not configured; no threat list was queried.",
            )
        url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={quote(key, safe='')}"
        payload = {
            "client": {"clientId": "trustlens-ai", "clientVersion": "1.0"},
            "threatInfo": {
                "threatTypes": [
                    "MALWARE",
                    "SOCIAL_ENGINEERING",
                    "UNWANTED_SOFTWARE",
                    "POTENTIALLY_HARMFUL_APPLICATION",
                ],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": f"https://{domain}/"}],
            },
        }
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code != 200:
                return _section("error", "Google Safe Browsing v4", [f"Safe Browsing returned HTTP {response.status_code}."], data={})
            matches = (response.json() or {}).get("matches") or []
            return _section(
                "ok",
                "Google Safe Browsing v4",
                [
                    "Google Safe Browsing APIs are restricted to non-commercial use under their terms; "
                    "confirm licensing before production use."
                ],
                confidence=0.9,
                data={"matches": fact(matches, source="Google Safe Browsing v4", confidence=0.9)},
            )
        except Exception as exc:
            return _section(
                "error",
                "Google Safe Browsing v4",
                [f"Safe Browsing lookup failed: {type(exc).__name__}: {exc}"],
                data={},
            )

    def _web_risk(self, domain: str) -> dict[str, Any]:
        key = str(setting(self.settings, "google_webrisk_api_key", "") or "").strip()
        if not key:
            return _not_configured("Google Web Risk v1", "GOOGLE_WEBRISK_API_KEY is not configured; no threat list was queried.")
        url = "https://webrisk.googleapis.com/v1/uris:search"
        params = {"key": key, "uri": f"https://{domain}/"}
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            if response.status_code != 200:
                return _section("error", "Google Web Risk v1", [f"Web Risk returned HTTP {response.status_code}."], data={})
            payload = response.json() or {}
            threat = payload.get("threat") or {}
            return _section(
                "ok",
                "Google Web Risk v1",
                ["Web Risk is a paid/commercial API with quota and terms restrictions; confirm licensing."],
                confidence=0.9,
                data={
                    "threat_types": fact(list(threat.get("types") or []), source="Google Web Risk v1", confidence=0.9),
                    "expire_time": fact(threat.get("expireTime"), source="Google Web Risk v1", confidence=0.9),
                },
            )
        except Exception as exc:
            return _section(
                "error",
                "Google Web Risk v1",
                [f"Web Risk lookup failed: {type(exc).__name__}: {exc}"],
                data={},
            )

    # ------------------------------------------------------------- Lookalikes
    @staticmethod
    def _lookalikes(domain: str) -> dict[str, Any]:
        label = domain.split(".", 1)[0] if domain else ""
        normalised = homoglyph_normalise(label)
        matches: list[dict[str, Any]] = []
        for brand in BRAND_NAMES:
            if normalised == brand:
                continue
            distance = levenshtein(normalised, brand)
            threshold = 1 if len(brand) <= 5 else 2
            prefix = normalised.startswith(brand) and 0 < len(normalised) - len(brand) <= 16
            embedded = brand in normalised and not prefix and len(normalised) - len(brand) <= 16
            if distance <= threshold or prefix or embedded:
                technique = (
                    "homoglyph/near-spelling" if distance <= threshold else ("brand+affix" if prefix else "brand embedded")
                )
                matches.append(
                    {
                        "brand": brand,
                        "technique": technique,
                        "edit_distance": distance,
                        "confidence": 0.45 if distance > 1 else 0.55,
                    }
                )
        return _section(
            "heuristic_match" if matches else "no_match",
            "local_edit_distance_and_homoglyph_heuristic",
            [
                "HEURISTIC ONLY: many legitimate brands, subsidiaries and regional domains resemble well-known names.",
                "A lookalike match alone is never treated as proof of malicious intent.",
            ],
            confidence=0.5,
            data={"matches": matches},
        )

    # --------------------------------------------------------------- Assembly
    @staticmethod
    def _fact_value(section: dict[str, Any] | None, key: str) -> Any:
        if not isinstance(section, dict):
            return None
        wrapped = (section.get("data") or {}).get(key)
        return wrapped.get("value") if isinstance(wrapped, dict) else None

    def _signals(
        self,
        rdap: dict[str, Any],
        dns: dict[str, Any],
        tls: dict[str, Any],
        threat: dict[str, Any],
        lookalikes: dict[str, Any],
    ) -> dict[str, Any]:
        registration = self._fact_value(rdap, "registration_date")
        registered_at = _parse_date(registration)
        age_days = int((utcnow() - registered_at).total_seconds() // 86400) if registered_at else None
        feed_matches = 0
        for name in ("virustotal", "safe_browsing", "web_risk"):
            section = threat.get(name) or {}
            if section.get("status") != "ok":
                continue
            data = section.get("data") or {}
            if name == "virustotal":
                feed_matches += int((data.get("malicious") or {}).get("value") or 0)
                feed_matches += int((data.get("suspicious") or {}).get("value") or 0)
            elif name == "safe_browsing":
                feed_matches += len((data.get("matches") or {}).get("value") or [])
            else:
                feed_matches += len((data.get("threat_types") or {}).get("value") or [])

        dns_data = dns.get("data") or {}
        return {
            "domain_age_days": {**fact(age_days, source="RDAP", confidence=0.8 if age_days is not None else 0.0),
                                "independently_verified": False},
            "recently_registered": {
                **fact(None if age_days is None else age_days < 30, source="RDAP", confidence=0.8 if age_days is not None else 0.0),
                "independently_verified": False,
            },
            "registrar": self._fact_value(rdap, "registrar"),
            "dns_records_present": fact(
                {
                    key: bool((wrapped or {}).get("value"))
                    for key, wrapped in dns_data.items()
                    if isinstance(wrapped, dict)
                },
                source="dnspython",
                confidence=0.85,
            ),
            "tls_valid": fact(
                self._fact_value(tls, "valid"),
                source="X.509 certificate / hostname check",
                confidence=0.9 if self._fact_value(tls, "valid") is not None else 0.0,
            ),
            "tls_days_to_expiry": fact(
                self._fact_value(tls, "days_to_expiry"),
                source="X.509 certificate",
                confidence=0.9 if self._fact_value(tls, "days_to_expiry") is not None else 0.0,
            ),
            "threat_feed_match_count": fact(
                feed_matches,
                source="configured threat feeds",
                confidence=0.8 if feed_matches else 0.0,
            ),
            "lookalike_brands": fact(
                [match["brand"] for match in (lookalikes.get("data") or {}).get("matches", [])],
                source="local lookalike heuristic",
                confidence=0.5,
            ),
            "weak_evidence_only": fact(
                bool((lookalikes.get("data") or {}).get("matches")) and feed_matches == 0,
                source="derived from heuristic and feed signals",
                confidence=0.4,
            ),
        }

    @staticmethod
    def _indicators(signals: dict[str, Any], rdap: dict[str, Any], tls: dict[str, Any], threat: dict[str, Any], lookalikes: dict[str, Any]) -> list[dict[str, Any]]:
        indicators: list[dict[str, Any]] = []
        if signals["recently_registered"]["value"] is True:
            indicators.append(
                make_indicator(
                    name="domain_recently_registered",
                    status="suspicious",
                    severity=0.35,
                    description="The domain was registered less than 30 days before observation; newly registered domains are over-represented in fraud, but many legitimate sites are new.",
                    source="RDAP",
                    confidence=0.6,
                )
            )
        matches = (lookalikes.get("data") or {}).get("matches") or []
        if matches:
            indicators.append(
                make_indicator(
                    name="domain_lookalike_heuristic",
                    status="suspicious",
                    severity=0.3,
                    description=f"Heuristic name similarity to well-known brand(s): {', '.join(match['brand'] for match in matches)}. Heuristic only; not proof of impersonation.",
                    source="local lookalike heuristic",
                    confidence=0.45,
                )
            )
        feed_count = int((signals.get("threat_feed_match_count") or {}).get("value") or 0)
        if feed_count >= 3:
            indicators.append(
                make_indicator(
                    name="domain_threat_feed_match",
                    status="confirmed_malicious",
                    severity=0.9,
                    description=f"Configured threat feeds reported {feed_count} malicious/suspicious detections for this domain.",
                    source="configured commercial threat feeds",
                    confidence=0.85,
                )
            )
        elif feed_count > 0:
            indicators.append(
                make_indicator(
                    name="domain_threat_feed_match",
                    status="suspicious",
                    severity=0.5,
                    description=f"A configured threat feed reported {feed_count} detection(s); corroboration is advisable.",
                    source="configured commercial threat feeds",
                    confidence=0.6,
                )
            )
        if (signals.get("tls_valid") or {}).get("value") is False:
            indicators.append(
                make_indicator(
                    name="tls_certificate_invalid",
                    status="verified_inconsistency",
                    severity=0.4,
                    description="The presented TLS certificate was expired, not yet valid, or did not match the hostname.",
                    source="pinned TLS connection",
                    confidence=0.85,
                    independently_verified=True,
                )
            )
        for section, name in ((rdap, "rdap"), (tls, "tls"), (threat.get("virustotal") or {}, "virustotal")):
            if section.get("status") in {"error", "blocked", "unavailable"}:
                indicators.append(
                    make_indicator(
                        name=f"{name}_technical_limitation",
                        status="technical_limitation",
                        severity=0.05,
                        description=f"{name} data could not be retrieved: {'; '.join(section.get('limitations', [])[:1]) or 'unknown error'}",
                        source=section.get("source", name),
                        confidence=0.9,
                    )
                )
        if signals["domain_age_days"]["value"] is None:
            indicators.append(
                make_indicator(
                    name="domain_registration_date_missing",
                    status="missing",
                    severity=0.0,
                    description="No registration date was available, so domain age could not be assessed.",
                    source="RDAP",
                    confidence=0.9,
                )
            )
        return indicators

    def analyse(self, url_or_domain: str, refresh: bool = False) -> dict[str, Any]:
        """Return domain intelligence for a URL or bare domain name."""
        host = (url_or_domain or "").strip()
        domain = registrable_domain(host)
        limitations: list[str] = []
        domains_repo = getattr(self.repos, "domains", None) if self.repos is not None else None

        if domains_repo is not None and domain and not refresh:
            try:
                cached = domains_repo.cached(domain, max_age_hours=int(setting(self.settings, "domain_refresh_interval_hours", 24)))
                if cached:
                    result = {key: value for key, value in cached.items() if key not in {"_id", "name_fingerprint"}}
                    result["from_cache"] = True
                    result.setdefault("limitations", []).append("Reused cached domain intelligence; no new external requests were made.")
                    return result
            except Exception as exc:
                limitations.append(f"Domain cache read failed: {type(exc).__name__}: {exc}")

        if not domain:
            result = {
                "status": "unavailable",
                "input": host,
                "domain": "",
                "checked_at": iso(),
                "from_cache": False,
                "rdap": _section("unavailable", "none", ["No registrable domain could be parsed from the input."], data={}),
                "dns": _section("unavailable", "none", ["No hostname was available for DNS resolution."], data={}),
                "tls": _section("unavailable", "none", ["No hostname was available for a TLS probe."], data={}),
                "threat_intel": {},
                "lookalikes": _section("no_match", "none", ["No domain was available."], data={"matches": []}),
                "signals": {},
                "indicators": [
                    make_indicator(
                        name="domain_not_parseable",
                        status="missing",
                        severity=0.0,
                        description="No registrable domain could be extracted from the supplied URL or hostname.",
                        source="input parsing",
                        confidence=0.9,
                    )
                ],
                "limitations": limitations,
                "sources_attempted": [],
                "sources_succeeded": [],
            }
            return result

        # Resolve the exact host from a URL (may include subdomain) for DNS/TLS,
        # while RDAP and reputation use the registrable domain.
        from urllib.parse import urlsplit

        try:
            parsed = urlsplit(host if "//" in host else f"https://{host}")
            query_host = (parsed.hostname or domain).strip().lower().rstrip(".")
        except ValueError:
            query_host = domain

        attempted = ["rdap.org", "dnspython", "pinned TLS"]
        rdap = self._rdap(domain)
        dns = self._dns(query_host)
        tls = self._tls(query_host)
        threat = {
            "virustotal": self._virustotal(domain),
            "safe_browsing": self._safe_browsing(domain),
            "web_risk": self._web_risk(domain),
        }
        lookalikes = self._lookalikes(domain)
        signals = self._signals(rdap, dns, tls, threat, lookalikes)

        succeeded = [name for name, section in (("rdap.org", rdap), ("dnspython", dns), ("pinned TLS", tls)) if section.get("status") == "ok"]
        succeeded.extend(
            name for name, section in threat.items() if section.get("status") == "ok"
        )
        for name in ("virustotal", "safe_browsing", "web_risk"):
            if threat[name].get("status") not in {"not_configured"}:
                attempted.append(name)

        result = {
            "status": "ok" if succeeded else "limited",
            "input": host,
            "domain": domain,
            "host": query_host,
            "checked_at": iso(),
            "from_cache": False,
            "rdap": rdap,
            "dns": dns,
            "tls": tls,
            "threat_intel": threat,
            "lookalikes": lookalikes,
            "signals": signals,
            "indicators": self._indicators(signals, rdap, tls, threat, lookalikes),
            "limitations": limitations,
            "sources_attempted": attempted,
            "sources_succeeded": succeeded,
        }

        if domains_repo is not None:
            try:
                domains_repo.upsert(domain, result)
            except Exception as exc:
                result["limitations"].append(f"Domain cache write failed: {type(exc).__name__}: {exc}")
        return result


__all__ = ["DomainAnalyser"]
