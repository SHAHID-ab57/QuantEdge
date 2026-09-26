"""`app.core.env_validation.find_duplicate_env_keys` (ENV-CONFIG-INTEGRITY).

Real `.env`-style files, written via `tmp_path` — not string parsing
exercised in the abstract, the same file format `Settings`' own
`env_file=".env"` loading actually reads.
"""

from pathlib import Path

import pytest

from app.core.env_validation import DuplicateEnvKey, find_duplicate_env_keys


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(content)
    return path


class TestFindDuplicateEnvKeys:
    def test_a_missing_file_returns_no_duplicates(self, tmp_path: Path) -> None:
        """A deployment with env vars injected directly and no `.env`
        file at all is not an error here."""
        assert find_duplicate_env_keys(tmp_path / "does-not-exist.env") == []

    def test_a_file_with_no_duplicates_returns_none(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "FOO=bar\nBAZ=qux\n")
        assert find_duplicate_env_keys(path) == []

    def test_comments_and_blank_lines_are_ignored(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# a comment\n\nFOO=bar\n\n# FOO=commented-out\n")
        assert find_duplicate_env_keys(path) == []

    def test_a_conflicting_duplicate_is_detected(self, tmp_path: Path) -> None:
        """The exact real incident's own shape: a real value, then a
        later, different (here: empty) redeclaration."""
        path = _write(
            tmp_path,
            "RETRAINING_EXPERIMENT_IDS=49bbf390-d038-4ed7-8b6c-bcd9a30754f8\n"
            "RETRAINING_SCHEDULER_ENABLED=true\n"
            "RETRAINING_EXPERIMENT_IDS=\n",
        )
        [duplicate] = find_duplicate_env_keys(path)
        assert duplicate.key == "RETRAINING_EXPERIMENT_IDS"
        assert duplicate.values_differ is True
        assert duplicate.occurrences == (
            (1, "49bbf390-d038-4ed7-8b6c-bcd9a30754f8"),
            (3, ""),
        )

    def test_the_effective_value_is_the_last_declaration(self, tmp_path: Path) -> None:
        """`python-dotenv`'s own resolution rule — confirmed empirically
        against this platform's real `.env` during the incident this
        module exists to catch, not assumed."""
        path = _write(tmp_path, "FOO=first\nFOO=second\nFOO=third\n")
        [duplicate] = find_duplicate_env_keys(path)
        assert duplicate.effective_value == "third"

    def test_an_identical_value_duplicate_is_reported_but_flagged_harmless(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, "FOO=bar\nFOO=bar\n")
        [duplicate] = find_duplicate_env_keys(path)
        assert duplicate.values_differ is False

    def test_a_key_declared_three_times_with_one_different_value_still_differs(
        self, tmp_path: Path
    ) -> None:
        path = _write(tmp_path, "FOO=bar\nFOO=bar\nFOO=baz\n")
        [duplicate] = find_duplicate_env_keys(path)
        assert duplicate.values_differ is True
        assert duplicate.effective_value == "baz"

    def test_multiple_distinct_duplicate_keys_are_all_reported(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "FOO=1\nFOO=2\nBAR=3\nBAR=3\nBAZ=unique\n")
        duplicates = {d.key: d for d in find_duplicate_env_keys(path)}
        assert set(duplicates) == {"FOO", "BAR"}
        assert duplicates["FOO"].values_differ is True
        assert duplicates["BAR"].values_differ is False

    def test_a_malformed_line_is_ignored_not_a_parse_error(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "not a valid line at all\nFOO=bar\n")
        assert find_duplicate_env_keys(path) == []


class TestDuplicateEnvKey:
    def test_values_differ_is_false_for_a_single_occurrence_key(self) -> None:
        # Not a realistic input from `find_duplicate_env_keys` itself
        # (which only ever returns keys seen more than once), but the
        # dataclass's own property must still behave sanely if used
        # directly.
        key = DuplicateEnvKey(key="FOO", occurrences=((1, "bar"),))
        assert key.values_differ is False
        assert key.effective_value == "bar"


class TestRealEnvFileRegression:
    """ENV-CONFIG-INTEGRITY's own regression test: pins the fix to the
    real incident, not just the general mechanism above. Skips cleanly
    if this environment has no local `.env` at all (CI, a fresh clone) —
    the same "skip, don't fail, when the precondition doesn't hold"
    posture `tests/repository/test_candles_postgres.py` already uses for
    its own real-Postgres dependency."""

    def test_retraining_experiment_ids_has_no_conflicting_duplicate_in_the_real_env_file(
        self,
    ) -> None:
        env_path = Path(".env")
        if not env_path.is_file():
            pytest.skip("no local .env file in this environment")

        conflicting = [
            d
            for d in find_duplicate_env_keys(env_path)
            if d.key == "RETRAINING_EXPERIMENT_IDS" and d.values_differ
        ]
        assert conflicting == [], (
            "RETRAINING_EXPERIMENT_IDS is declared more than once with conflicting "
            "values in the real .env -- this is the exact incident ENV-CONFIG-INTEGRITY "
            f"fixed: {conflicting}"
        )
