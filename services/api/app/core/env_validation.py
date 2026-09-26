"""Detects `.env` drift that `pydantic-settings` would otherwise resolve
silently — ENV-CONFIG-INTEGRITY: `RETRAINING_EXPERIMENT_IDS` sat silently
nullified by a duplicate, later, empty declaration in the real local
`.env` for an unknown number of days before anyone noticed, because
nothing ever checked. `python-dotenv` (which `pydantic-settings`'
`env_file` loading uses under the hood) resolves a duplicate key to its
*last* declaration with no warning — confirmed empirically against this
platform's own real `.env` during the incident this module exists to
catch. This module parses the raw file independently of `Settings`
(which has already resolved — possibly silently wrong — by the time a
caller could otherwise ask it, since `get_settings()` is called well
before any validation step could run), so it can flag the problem
regardless of import order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_KEY_VALUE_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True, slots=True)
class DuplicateEnvKey:
    """One key declared more than once in an `.env`-style file."""

    key: str
    #: `(line_number, raw_value)` for every declaration, in file order —
    #: the *last* one is the one actually in effect (`python-dotenv`'s
    #: own resolution rule, not this platform's choice).
    occurrences: tuple[tuple[int, str], ...]

    @property
    def values_differ(self) -> bool:
        """True when the duplicate declarations don't even agree with
        each other — the dangerous case (a real value silently replaced
        by a different one), not merely harmless redundancy."""
        return len({value for _, value in self.occurrences}) > 1

    @property
    def effective_value(self) -> str:
        """What `python-dotenv` actually resolves this key to: the last
        declaration in the file."""
        return self.occurrences[-1][1]


def find_duplicate_env_keys(path: str | Path) -> list[DuplicateEnvKey]:
    """Every key declared more than once in the `.env`-style file at
    `path`, in the order first seen.

    Returns `[]` if the file doesn't exist — a deployment with env vars
    injected directly and no `.env` file at all is not an error here —
    or if it has no duplicates. Comments (`#...`) and blank lines are
    skipped; a line that isn't a recognizable `KEY=VALUE` declaration is
    silently ignored rather than treated as a parse error, since this
    check's only job is duplicate detection, not full `.env` validation.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return []

    occurrences_by_key: dict[str, list[tuple[int, str]]] = {}
    for line_number, raw_line in enumerate(file_path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _KEY_VALUE_PATTERN.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        occurrences_by_key.setdefault(key, []).append((line_number, value))

    return [
        DuplicateEnvKey(key=key, occurrences=tuple(occurrences))
        for key, occurrences in occurrences_by_key.items()
        if len(occurrences) > 1
    ]
