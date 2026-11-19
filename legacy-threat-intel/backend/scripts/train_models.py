"""CLI: train and register ML models from verified labeled MongoDB data.

Usage (inside backend container):
    python -m scripts.train_models
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.mongo import MongoDBService  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402
from app.detection.ml import train_models  # noqa: E402
from app.utils import json_safe  # noqa: E402


def main() -> int:
    settings = get_settings()
    mongo = MongoDBService(settings)
    try:
        mongo.connect()
        result = train_models(settings, Repositories(mongo))
        print(json.dumps(json_safe(result), indent=2, default=str))
        return 0 if result.get("status") == "trained" else 2
    finally:
        mongo.close()


if __name__ == "__main__":
    raise SystemExit(main())
