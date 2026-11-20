"""Logical MongoDB backup, verification and restore for TrustLens AI.

This is a real, dependency-light tool: each collection is exported as JSON Lines
using BSON's extended JSON, a manifest records document counts and SHA-256
hashes, and restore refuses to run without explicit confirmation. It works with
any PyMongo-compatible client, which lets the drill be tested with mongomock.

Backups contain personal data. Keep them outside the web root, restrict file
permissions and encrypt them at rest; this tool does not encrypt output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo import MongoClient

FORMAT = "trustlens-logical-backup-v1"
MANIFEST = "manifest.json"


class BackupError(RuntimeError):
    """Raised when a backup is missing, corrupt or inconsistent."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_backup(client: Any, db_name: str, output_dir: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    stamp = (now or _utcnow()).strftime("%Y%m%dT%H%M%SZ")
    target = Path(output_dir) / f"trustlens-{stamp}"
    if target.exists():
        raise BackupError(f"backup target already exists: {target}")
    target.mkdir(parents=True)

    manifest: dict[str, Any] = {
        "format": FORMAT,
        "created_at": (now or _utcnow()).isoformat(),
        "database": db_name,
        "collections": {},
    }
    db = client[db_name]
    for name in sorted(db.list_collection_names()):
        path = target / f"{name}.jsonl"
        digest = hashlib.sha256()
        count = 0
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for document in db[name].find({}):
                line = json_util.dumps(document, ensure_ascii=False)
                handle.write(line + "\n")
                digest.update((line + "\n").encode("utf-8"))
                count += 1
        manifest["collections"][name] = {
            "file": path.name,
            "documents": count,
            "sha256": digest.hexdigest(),
        }

    (target / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "status": "ok",
        "path": str(target),
        "collections": len(manifest["collections"]),
        "documents": sum(item["documents"] for item in manifest["collections"].values()),
    }


def _read_manifest(backup_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    target = Path(backup_dir)
    manifest_path = target / MANIFEST
    if not manifest_path.is_file():
        raise BackupError(f"missing {MANIFEST} in {target}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError(f"unreadable manifest: {exc}") from exc
    if manifest.get("format") != FORMAT:
        raise BackupError("unsupported backup format")
    if not isinstance(manifest.get("collections"), dict):
        raise BackupError("manifest has no collections map")
    return target, manifest


def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    target, manifest = _read_manifest(backup_dir)
    checked: dict[str, int] = {}
    for name, meta in manifest["collections"].items():
        path = target / str(meta.get("file", ""))
        if not path.is_file():
            raise BackupError(f"missing collection file: {name}")
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as handle:
            for line in handle:
                digest.update(line)
                count += 1
        if digest.hexdigest() != meta.get("sha256") or count != meta.get("documents"):
            raise BackupError(f"checksum or document count mismatch: {name}")
        checked[name] = count
    return {
        "status": "ok",
        "collections": len(checked),
        "documents": sum(checked.values()),
        "database": manifest.get("database", ""),
    }


def restore_backup(
    client: Any,
    db_name: str,
    backup_dir: str | Path,
    *,
    confirm: bool = False,
    drop: bool = False,
) -> dict[str, Any]:
    if not confirm:
        return {"status": "refused", "reason": "explicit --confirm is required", "restored": {}}
    target, manifest = _read_manifest(backup_dir)
    verify_backup(target)
    # The destination database is chosen explicitly with --db, which makes
    # restore-to-a-scratch-database drills possible. --confirm remains mandatory.
    db = client[db_name]
    restored: dict[str, int] = {}
    for name, meta in manifest["collections"].items():
        collection = db[name]
        if drop:
            collection.drop()
        path = target / str(meta["file"])
        count = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                collection.insert_one(json_util.loads(line))
                count += 1
        restored[name] = count
    return {
        "status": "ok",
        "database": db_name,
        "restored": restored,
        "total_restored": sum(restored.values()),
        "dropped_first": drop,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TrustLens AI logical backup tool")
    parser.add_argument("command", choices=("create", "verify", "restore"))
    parser.add_argument("--uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="hireshield")
    parser.add_argument("--out", default="backups", help="parent directory for create")
    parser.add_argument("--dir", help="backup directory for verify/restore")
    parser.add_argument("--confirm", action="store_true", help="required for restore")
    parser.add_argument("--drop", action="store_true", help="drop collections before restore")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            client = MongoClient(args.uri, serverSelectionTimeoutMS=5000)
            try:
                result = create_backup(client, args.db, args.out)
            finally:
                client.close()
        elif args.command == "verify":
            if not args.dir:
                raise BackupError("--dir is required for verify")
            result = verify_backup(args.dir)
        else:
            if not args.dir:
                raise BackupError("--dir is required for restore")
            client = MongoClient(args.uri, serverSelectionTimeoutMS=5000)
            try:
                result = restore_backup(
                    client, args.db, args.dir, confirm=args.confirm, drop=args.drop
                )
            finally:
                client.close()
    except (BackupError, OSError) as exc:
        print(f"backup {args.command} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
