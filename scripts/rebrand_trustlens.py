"""One-way rebrand migration: HireShield AI -> TrustLens AI.

This script exists as an auditable record of the Stage 2 rebrand. It replaces
user-facing product identity while deliberately preserving infrastructure
identifiers whose change would break data, deployments or provenance:

  * live Render service names and hostnames
  * MongoDB database name and Compose project/volume names
  * seeded demo account email addresses
  * Celery namespace
  * published container image names and CI artifact names
  * approved model manifest provenance
  * live URLs embedded in the grounded support FAQ

Protected lines are skipped wholesale. Files under EXCLUDED are not touched.
Run from the repository root: python scripts/rebrand_trustlens.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTECTED = (
    "hireshield-web-j72o",
    "hireshield-api-wets",
    "hireshield-backend",
    "hireshield-api",
    "hireshield-web",
    "name: hireshield-ai",
    "hireshield-ai_",
    "hireshield-ai-api",
    "hireshield-ai-web",
    "mongodb_db: str = \"hireshield\"",
    "MONGODB_DB=hireshield",
    "MONGODB_DB:-hireshield",
    "- key: MONGODB_DB",
    "celery_app = Celery(",
    "curated_synthetic_messages",
    "demo@hireshield.io",
    "admin@hireshield.io",
    "namespace=\"hireshield\"",
    "namespace='hireshield'",
    "ghcr.io/",
    "github.com/",
    "hireshield-ai:latest",
    "model_manifest.json",
)

REPLACEMENTS = (
    ("Hire Shield", "TrustLens"),
    ("HireShield", "TrustLens"),
    ("hireshield", "trustlens"),
    ("HIRESHIELD", "TRUSTLENS"),
)

INCLUDED_DIRS = (
    Path("frontend/src"),
    Path("backend/app"),
    Path("backend/scripts"),
    Path("docs"),
)

INCLUDED_FILES = (
    Path("frontend/index.html"),
    Path("frontend/package.json"),
    Path("frontend/package-lock.json"),
    Path("frontend/.env.example"),
    Path("backend/app/main.py"),
    Path(".env.example"),
    Path("docker-compose.yml"),
    Path("render.yaml"),
    Path("README.md"),
    Path("DEVELOPMENT_STATUS.md"),
)

EXCLUDED = {
    Path("docs/TRUSTLENS_ROADMAP.md"),       # historical baseline references are intentional
    Path("docs/TRUSTLENS_ARCHITECTURE.md"),  # baseline description is intentional
    Path("backend/app/support/faq.py"),      # contains live URLs; handled by targeted edits
}


def is_protected(line: str) -> bool:
    lowered = line.lower()
    return any(token.lower() in lowered for token in PROTECTED)


def convert(text: str) -> tuple[str, int]:
    output: list[str] = []
    changed_lines = 0
    for line in text.splitlines(keepends=True):
        if is_protected(line):
            output.append(line)
            continue
        updated = line
        for old, new in REPLACEMENTS:
            updated = updated.replace(old, new)
        if updated != line:
            changed_lines += 1
        output.append(updated)
    return "".join(output), changed_lines


def main() -> None:
    targets: list[Path] = []
    for directory in INCLUDED_DIRS:
        base = ROOT / directory
        if base.is_dir():
            targets.extend(
                p for p in base.rglob("*")
                if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".md", ".html", ".json", ".example"}
            )
    targets.extend(ROOT / p for p in INCLUDED_FILES if (ROOT / p).exists())

    seen: set[Path] = set()
    total_files = 0
    total_lines = 0
    for path in sorted(set(targets)):
        relative = path.relative_to(ROOT)
        if relative in EXCLUDED or any(part in {".git", "node_modules", "__pycache__", "dist"} for part in relative.parts):
            continue
        if path in seen:
            continue
        seen.add(path)
        original = path.read_text(encoding="utf-8")
        updated, changed = convert(original)
        if changed:
            path.write_text(updated, encoding="utf-8")
            total_files += 1
            total_lines += changed
            print(f"{relative}: {changed} line(s)")

    print(f"\nRebranded {total_lines} line(s) across {total_files} file(s).")


if __name__ == "__main__":
    main()
