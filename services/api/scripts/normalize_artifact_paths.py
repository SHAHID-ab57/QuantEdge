"""One-off: normalize training_jobs.result_summary artifact references from
absolute file:// URIs (the training machine's own filesystem, meaningless
anywhere else — see app/training/serialization.py's own docstring for the
production incident this caused) to paths relative to model_artifact_dir.

Real production bug, not hypothetical: paper trading's automated strategy
failed with FileNotFoundError on the server because a job's artifact_uri
was still the developer laptop's own absolute home-directory path. This
script rewrites every already-stored row so it works on *any* machine
going forward, not just future training runs (which already write the
relative form as of the fix this script accompanies).

Idempotent: rows already using the relative form are left untouched, so
running this more than once (or against a database with a mix of old and
already-normalized rows) is always safe.

Usage:
    uv run python scripts/normalize_artifact_paths.py            # apply
    uv run python scripts/normalize_artifact_paths.py --dry-run   # preview only
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import setup_logging
from app.db.engine import get_engine
from app.models.training import TrainingJob


def _normalize(uri: str) -> str:
    """Same legacy-parsing rule as `resolve_artifact_uri` — kept in sync
    deliberately (not imported), since that function resolves against
    *this* environment's directory at read time, while this script only
    ever needs the bare relative reference to write back to the row.
    """
    if not uri.startswith("file://"):
        return uri
    legacy_path = Path.from_uri(uri)
    if legacy_path.parent.name == "reports":
        return f"reports/{legacy_path.name}"
    return legacy_path.name


def _normalize_summary(summary: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    new_summary = dict(summary)
    artifact_uri = new_summary.get("artifact_uri")
    if isinstance(artifact_uri, str) and artifact_uri.startswith("file://"):
        new_summary["artifact_uri"] = _normalize(artifact_uri)
        changed = True
    artifacts = new_summary.get("artifacts")
    if isinstance(artifacts, dict):
        new_artifacts = dict(artifacts)
        for key, value in artifacts.items():
            if isinstance(value, str) and value.startswith("file://"):
                new_artifacts[key] = _normalize(value)
                changed = True
        new_summary["artifacts"] = new_artifacts
    return new_summary, changed


async def main(dry_run: bool) -> None:
    setup_logging()
    engine = get_engine()
    if engine is None:
        print("DATABASE_URL is not configured — nothing to do.")
        sys.exit(1)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (await session.execute(select(TrainingJob))).scalars().all()
        touched = 0
        for job in rows:
            summary = job.result_summary
            if not isinstance(summary, dict):
                continue
            new_summary, changed = _normalize_summary(summary)
            if not changed:
                continue
            touched += 1
            action = "[dry-run] would normalize" if dry_run else "normalizing"
            print(f"{action} job {job.id}")
            old_uri, new_uri = summary.get("artifact_uri"), new_summary.get("artifact_uri")
            print(f"  artifact_uri: {old_uri!r} -> {new_uri!r}")
            old_artifacts = summary.get("artifacts") or {}
            new_artifacts = new_summary.get("artifacts") or {}
            for key in old_artifacts:
                old_val, new_val = old_artifacts.get(key), new_artifacts.get(key)
                if old_val != new_val:
                    print(f"  artifacts[{key!r}]: {old_val!r} -> {new_val!r}")
            if not dry_run:
                job.result_summary = new_summary
        if not dry_run and touched:
            await session.commit()

    print(
        f"\n{touched} job(s) {'would be' if dry_run else 'were'} normalized "
        f"out of {len(rows)} total training_jobs rows."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
