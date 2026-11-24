"""Loader for the MIT-licensed DIFrauD deception benchmark.

Source: https://huggingface.co/datasets/difraud/difraud

DIFrauD contains real, intentionally harmful text from seven independent
domains. Only the domain subsets explicitly requested by the caller are read.
The dataset is distributed under the MIT license. Raw text is deliberately NOT
committed to this repository: it may contain real names, contact details and
malicious links. Email local-parts and phone-like digit sequences are redacted
before training, but residual personal data may remain, so the cleaned corpus
must stay outside version control.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.ml.features import normalize_text

logger = logging.getLogger(__name__)

DATASET_REPO_ID = "difraud/difraud"
DATASET_URL = "https://huggingface.co/datasets/difraud/difraud"
DATASET_REVISION = "main"
DATASET_LICENSE = "MIT"

ALL_DOMAINS = (
    "fake_news",
    "job_scams",
    "phishing",
    "political_statements",
    "product_reviews",
    "sms",
    "twitter_rumours",
)
MESSAGE_DOMAINS: tuple[str, ...] = ("phishing", "sms")
JOB_DOMAINS: tuple[str, ...] = ("job_scams",)

SPLITS = ("train", "validation", "test")

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().\-]{7,}\d)(?!\w)")


def resolve_difraud_dir(data_dir: str) -> Path | None:
    """Locate a downloaded DIFrauD tree under ``data_dir`` only.

    Deliberately does not search the backend root. This keeps training
    reproducible from an explicit data directory and prevents an unrelated
    download from silently changing test outcomes.
    """
    given = Path(data_dir).expanduser()
    candidates = [
        given / "datasets" / "difraud",
        given / "difraud",
        Path.cwd() / given / "datasets" / "difraud",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def scrub_personal_data(text: str) -> str:
    """Redact obvious direct identifiers while preserving useful domains/signals."""
    cleaned = _EMAIL_RE.sub(r"[EMAIL]@\1", text)
    cleaned = _PHONE_RE.sub("[PHONE]", cleaned)
    return cleaned


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_split(path: Path) -> pd.DataFrame:
    texts: list[str] = []
    labels: list[int] = []
    invalid = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                raw_text = str(row.get("text") or "")
                raw_label = int(row.get("label"))
            except (json.JSONDecodeError, TypeError, ValueError):
                invalid += 1
                continue
            if raw_label not in (0, 1) or not raw_text.strip():
                invalid += 1
                continue
            # Normalisation already replaces contact details with sentinel
            # tokens. Scrub afterwards as a safety net for anything its regexes
            # missed, without destroying those sentinels.
            cleaned = scrub_personal_data(normalize_text(raw_text))
            if len(cleaned) < 20:
                invalid += 1
                continue
            texts.append(cleaned)
            labels.append(raw_label)
    frame = pd.DataFrame({"text": texts, "label": labels})
    return frame.drop_duplicates(subset=["text"], keep="first").reset_index(drop=True)


def load_difraud_dataset(
    data_dir: str,
    domains: tuple[str, ...] | list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
    """Read the requested DIFrauD domains using the benchmark's own splits.

    Returns ``(train, validation, test, provenance)`` or ``None`` when the
    dataset is not present. Cross-split duplicate texts are removed so that a
    posting cannot appear in both training and evaluation.
    """
    root = resolve_difraud_dir(data_dir)
    if root is None:
        return None

    selected = tuple(domains or MESSAGE_DOMAINS)
    unknown = [name for name in selected if name not in ALL_DOMAINS]
    if unknown:
        raise ValueError(f"unknown DIFrauD domains: {unknown}")

    frames: dict[str, pd.DataFrame] = {}
    source_files: dict[str, dict[str, str]] = {}
    raw_rows: dict[str, int] = {}
    for split in SPLITS:
        parts: list[pd.DataFrame] = []
        files: dict[str, str] = {}
        for domain in selected:
            path = root / domain / f"{split}.jsonl"
            if not path.is_file():
                raise FileNotFoundError(f"DIFrauD split not found: {path}")
            parts.append(_read_split(path))
            files[domain] = str(path.resolve())
            source_files.setdefault(split, {})[domain] = str(path)
        merged = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"text": [], "label": []})
        merged = merged.drop_duplicates(subset=["text"], keep="first").reset_index(drop=True)
        frames[split] = merged
        raw_rows[split] = int(len(merged))

    train_texts = set(frames["train"]["text"])
    for split in ("validation", "test"):
        overlap = frames[split]["text"].isin(train_texts)
        frames[split] = frames[split][~overlap].reset_index(drop=True)

    for split in SPLITS:
        counts = frames[split]["label"].value_counts().to_dict()
        if len(counts) < 2:
            raise ValueError(f"DIFrauD {split} split has only one class for {selected}")

    hashed = hashlib.sha256("|".join(sorted(source_files.get("train", {}).values())).encode()).hexdigest()[:12]
    provenance: dict[str, Any] = {
        "name": "difraud_v1",
        "dataset": DATASET_REPO_ID,
        "url": DATASET_URL,
        "revision": DATASET_REVISION,
        "license": DATASET_LICENSE,
        "domains": list(selected),
        "real_world_data": True,
        "production_grade": False,
        "source_files": source_files,
        "source_sha256": {split: {d: _file_sha256(Path(p)) for d, p in files.items()} for split, files in source_files.items()},
        "raw_rows": raw_rows,
        "class_counts": {
            split: {str(k): int(v) for k, v in frames[split]["label"].value_counts().to_dict().items()}
            for split in SPLITS
        },
        "fingerprint": hashed,
        "personal_data_handling": (
            "Email local-parts, phone-like digit sequences and duplicate texts were redacted/removed. "
            "Residual personal data may remain; raw JSONL is gitignored and never committed."
        ),
        "notes": (
            "Third-party public research benchmark. Labels are curated for general deception, "
            "not for this product's threat model; validate on local traffic before making absolute claims."
        ),
    }
    return frames["train"], frames["validation"], frames["test"], provenance


def difraud_limitations(domains: tuple[str, ...] | list[str]) -> list[str]:
    return [
        "Trained on the third-party DIFrauD research benchmark; deception labels are curated for research, "
        "not verified against TrustLens production traffic.",
        f"Only the following DIFrauD domains were used: {', '.join(domains)}. Cross-domain generalisation is unvalidated.",
        "Direct identifiers were redacted, but residual personal data or malicious links in the source text may remain.",
        "Text-only signal: no independent verification of employer, domain, sender or campaign is performed.",
        "Scores are uncalibrated ranking values and must be used as decision support, never as proof of fraud.",
    ]
