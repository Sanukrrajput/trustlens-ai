"""CLI entrypoint for offline model training.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe backend/scripts/train_models.py

Optional overrides:

    --data-dir backend/data     --model-dir backend/models
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.ml.training.train import train_all  # noqa: E402


def _resolve_storage_path(value: str) -> str:
    """Resolve a settings-style relative path against the backend directory."""
    path = Path(value).expanduser()
    if path.is_absolute() or path.exists():
        return str(path)
    return str(BACKEND_ROOT / path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train and publish TrustLens AI models")
    parser.add_argument("--data-dir", default=None, help="Dataset directory (default: settings.data_dir)")
    parser.add_argument("--model-dir", default=None, help="Artifact directory (default: settings.model_dir)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument(
        "--no-difraud",
        action="store_true",
        help="Skip the optional DIFrauD corpus and train legacy families only",
    )
    parser.add_argument(
        "--message-domains",
        default="phishing,sms",
        help="Comma-separated DIFrauD domains for the message model (default: phishing,sms)",
    )
    parser.add_argument(
        "--job-domains",
        default="job_scams",
        help="Comma-separated DIFrauD domains for the job model (default: job_scams)",
    )
    return parser


def _parse_domains(value: str) -> tuple[str, ...]:
    """Parse a comma-separated domain list from the CLI into a clean tuple."""
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    settings = Settings()
    data_dir = args.data_dir or _resolve_storage_path(settings.data_dir)
    model_dir = args.model_dir or _resolve_storage_path(settings.model_dir)
    summary = train_all(
        data_dir=data_dir,
        model_dir=model_dir,
        include_difraud=not args.no_difraud,
        difraud_domains={
            "message": _parse_domains(args.message_domains),
            "job": _parse_domains(args.job_domains),
        },
    )
    print(json.dumps(summary, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
