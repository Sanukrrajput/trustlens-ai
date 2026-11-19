"""OPTIONAL local validation helper: generate SYNTHETIC authorized application logs.

This is NOT used by the platform by default and must only be run against a path
you own, configured as APPLICATION_LOG_PATH. Generated events are unlabeled and
must never be represented as real attacks or used as validated ML ground truth.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import timedelta
from pathlib import Path

from app.utils import to_iso, utcnow


def main() -> None:
    parser = argparse.ArgumentParser(description="Write synthetic JSONL events to an authorized local file")
    parser.add_argument("path", type=Path, help="file you own (set APPLICATION_LOG_PATH to the same value)")
    parser.add_argument("--count", type=int, default=200)
    args = parser.parse_args()

    rng = random.Random(20261118)
    now = utcnow()
    attacker = "198.51.100.77"  # documentation-range address, not a real host
    normal_users = ["alice", "bob", "carol", "dave"]
    lines: list[str] = []
    for index in range(args.count):
        event_time = now - timedelta(minutes=args.count - index)
        if index >= args.count - 40:
            user = rng.choice(["admin", "root", "svc_backup"])
            event_type = "auth" if index % 3 else "api_request"
            outcome = "failure" if index % 4 else "success"
            source_ip = attacker
        else:
            user = rng.choice(normal_users)
            event_type = "auth" if index % 5 else "api_request"
            outcome = "success" if rng.random() > 0.08 else "failure"
            source_ip = f"10.20.0.{rng.randint(2, 40)}"
        record = {
            "timestamp": to_iso(event_time),
            "event_type": event_type,
            "outcome": outcome,
            "source_ip": source_ip,
            "actor_user": user,
            "destination_host": "app-server-01",
            "message": "SYNTHETIC validation event - not a real incident",
            "tags": ["synthetic_validation_only"],
        }
        lines.append(json.dumps(record))
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} SYNTHETIC events to {args.path}")
    print("Set APPLICATION_LOG_PATH to this file, add application_log to AUTHORIZED_SOURCES and ENABLED_SOURCES, then run collection.")


if __name__ == "__main__":
    main()
