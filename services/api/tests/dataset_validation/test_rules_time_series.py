"""Time-series rule tests — timestamp ordering and gaps."""

from datetime import UTC, datetime, timedelta

from app.dataset_validation.base import ValidationContext
from app.dataset_validation.rules.time_series import TimeGapsRule, TimestampOrderingRule
from tests.dataset_validation.conftest import make_dataset

BASE = datetime(2026, 1, 1, tzinfo=UTC)


class TestTimestampOrderingRule:
    def test_clean_ascending_series_has_no_issues(self) -> None:
        timestamps = [BASE + timedelta(hours=i) for i in range(4)]
        dataset = make_dataset(timestamps=timestamps, rows=[[float(i)] for i in range(4)])
        assert TimestampOrderingRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_an_out_of_order_pair(self) -> None:
        timestamps = [BASE, BASE + timedelta(hours=2), BASE + timedelta(hours=1)]
        dataset = make_dataset(timestamps=timestamps, rows=[[1.0], [2.0], [3.0]])
        issues = TimestampOrderingRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "timestamp_ordering"
        assert issues[0].row_index == 2
        assert issues[0].severity == "error"

    def test_a_repeated_timestamp_also_counts_as_out_of_order(self) -> None:
        # Strictly increasing means a tie is a violation too — this rule's
        # concern is order, not uniqueness (DuplicateTimestampsRule owns that).
        timestamps = [BASE, BASE, BASE + timedelta(hours=1)]
        dataset = make_dataset(timestamps=timestamps, rows=[[1.0], [2.0], [3.0]])
        issues = TimestampOrderingRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].row_index == 1

    def test_single_row_dataset_is_trivially_ordered(self) -> None:
        dataset = make_dataset(timestamps=[BASE], rows=[[1.0]])
        assert TimestampOrderingRule().check(ValidationContext(dataset=dataset)) == []


class TestTimeGapsRule:
    def test_no_gaps_has_no_issues(self) -> None:
        timestamps = [BASE + timedelta(hours=i) for i in range(4)]
        dataset = make_dataset(
            timestamps=timestamps, rows=[[float(i)] for i in range(4)], timeframe="1h"
        )
        assert TimeGapsRule().check(ValidationContext(dataset=dataset)) == []

    def test_flags_a_missing_bucket(self) -> None:
        # 03:00 is missing from an otherwise-hourly series.
        timestamps = [
            BASE,
            BASE + timedelta(hours=1),
            BASE + timedelta(hours=2),
            BASE + timedelta(hours=4),
        ]
        dataset = make_dataset(
            timestamps=timestamps, rows=[[1.0], [2.0], [3.0], [4.0]], timeframe="1h"
        )
        issues = TimeGapsRule().check(ValidationContext(dataset=dataset))
        assert len(issues) == 1
        assert issues[0].code == "time_gaps"
        assert issues[0].count == 1
        assert issues[0].severity == "warning"
