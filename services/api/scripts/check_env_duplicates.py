"""CI-usable duplicate-key check for `.env.example` (ENV-CONFIG-INTEGRITY).

Complementary to, and much weaker than, the real-time check
`app.core.env_validation`/`app.application._check_env_duplicates` runs
against the real `.env` at every startup: `.env` is gitignored and
per-environment (`configs/README.md`), so this script — run in CI,
against the committed `.env.example` template only — can never see the
actual incident this whole task exists because of (a duplicate key in a
real, local, untracked `.env`). It exists anyway because the template
itself is a real, checked-in artifact that could accumulate the
identical mistake, and catching that before merge is cheap.

Usage:
    uv run python scripts/check_env_duplicates.py [path ...]

Defaults to `.env.example` (relative to the current working directory —
CI runs this from `services/api`, matching every other `services/api`
gate) when no path is given. Exit code 1 if any file has a conflicting
duplicate (declarations that disagree); a harmless duplicate (identical
values on every declaration) only prints a warning and doesn't fail the
check. Exit code 0 otherwise.
"""

import sys

from app.core.env_validation import find_duplicate_env_keys


def main() -> int:
    paths = sys.argv[1:] or [".env.example"]
    exit_code = 0
    for path in paths:
        for duplicate in find_duplicate_env_keys(path):
            if duplicate.values_differ:
                declarations = ", ".join(
                    f"line {line_number}={value!r}" for line_number, value in duplicate.occurrences
                )
                print(f"{path}: CONFLICTING duplicate key {duplicate.key} ({declarations})")
                exit_code = 1
            else:
                print(
                    f"{path}: {duplicate.key} declared {len(duplicate.occurrences)} times "
                    "with the identical value (harmless, but worth cleaning up)"
                )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
