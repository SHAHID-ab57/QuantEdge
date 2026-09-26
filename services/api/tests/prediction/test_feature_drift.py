"""Unit tests for `compute_feature_drift` (FEATURE-DRIFT-MONITOR).

`TestKnownDriftIncidents` uses the real, already-measured numbers from
`docs/research/FEATURE_DRIFT_INVESTIGATION.md` — both real training jobs'
own stored normalization and both real live feature readings the
investigation checked directly — rather than synthetic fixtures alone, the
same "prove it against the real case, not just a made-up one" discipline
this platform's own research thread has used throughout.
"""

import pytest

from app.prediction.feature_drift import DRIFT_Z_THRESHOLD, compute_feature_drift


def stat(column: str, mean: float, std: float) -> dict[str, object]:
    return {"column": column, "mean": mean, "std": std, "minimum": None, "maximum": None}


#: Job `733082cc`'s own real stored normalization (2024-02-06 -> 2024-11-01).
_733082CC_NORMALIZATION = [
    stat("open", 3290.171249166481, 374.6269365530849),
    stat("high", 3303.947466103579, 375.7832604973196),
    stat("low", 3274.7448544120916, 373.9171854018892),
    stat("close", 3290.025127806179, 374.56893314626194),
    stat("volume", 12708.210268948655, 18859.53277441502),
    stat("sma_20", 3289.4851922649473, 373.3165850433633),
]

#: Job `6e7fb4ed`'s own real stored normalization (100 most recent candles,
#: fit 2026-09-09).
_6E7FB4ED_NORMALIZATION = [
    stat("open", 2488.3307142857143, 15.373196277141282),
    stat("high", 2495.217857142857, 16.479402805828087),
    stat("low", 2481.705, 14.336482309130076),
    stat("close", 2488.599285714286, 14.962513856914807),
    stat("volume", 882610.6857142857, 562040.1211550533),
    stat("sma_20", 2484.3515714285713, 15.744374035845684),
]


class TestKnownDriftIncidents:
    def test_733082cc_volume_drift_is_flagged_drifted(self) -> None:
        """The real live reading measured 2026-09-22: z(volume) = +88.96,
        while every price/SMA column sat at a mild, in-band -1.4 to -1.5 —
        `volume` alone must be the one that trips this."""
        report = compute_feature_drift(
            live_values={
                "open": 2741.75,
                "high": 2754.95,
                "low": 2735.50,
                "close": 2742.95,
                "volume": 1690478.0,
                "sma_20": 2748.73,
            },
            normalization=_733082CC_NORMALIZATION,
        )
        assert report.status == "drifted"
        assert report.worst_feature == "volume"
        assert report.worst_z == pytest.approx(88.96, abs=0.05)
        # Every price/SMA column stays comfortably inside the threshold —
        # this is a one-feature incident, not a wholesale blowup.
        for column in ("open", "high", "low", "close", "sma_20"):
            assert abs(report.z_scores[column]) < DRIFT_Z_THRESHOLD

    def test_6e7fb4ed_price_and_sma_drift_is_flagged_drifted(self) -> None:
        """The real live reading for the *other* live job: price/SMA at +15
        to +18, `volume` itself mild (+1.44) — the reverse pattern from
        `733082cc`, proving this check is not secretly volume-specific."""
        report = compute_feature_drift(
            live_values={
                "open": 2741.75,
                "high": 2754.95,
                "low": 2735.50,
                "close": 2742.95,
                "volume": 1690478.0,
                "sma_20": 2748.73,
            },
            normalization=_6E7FB4ED_NORMALIZATION,
        )
        assert report.status == "drifted"
        assert report.worst_feature == "low"  # the single largest measured: z = +17.70
        assert report.worst_z == pytest.approx(17.70, abs=0.05)
        assert abs(report.z_scores["volume"]) < DRIFT_Z_THRESHOLD
        # Every price/SMA column is itself far past the threshold, not just
        # the reported worst one.
        for column in ("open", "high", "close", "sma_20"):
            assert abs(report.z_scores[column]) >= DRIFT_Z_THRESHOLD

    def test_a_held_out_in_window_reading_reads_healthy(self) -> None:
        """The genuinely healthy reference this threshold was set against:
        `733082cc`'s own held-out test-split max was |z|=9.32 (volume) /
        2.6 (price) — nowhere close to either real incident."""
        report = compute_feature_drift(
            live_values={
                "open": 3295.0,
                "high": 3310.0,
                "low": 3270.0,
                "close": 3290.0,
                "volume": 50000.0,  # ~2 sigma from the training mean, not 89
                "sma_20": 3289.0,
            },
            normalization=_733082CC_NORMALIZATION,
        )
        assert report.status == "healthy"
        assert report.worst_feature is not None
        assert abs(report.worst_z or 0) < DRIFT_Z_THRESHOLD


class TestCompareFeatureDrift:
    def test_a_value_exactly_at_the_training_mean_has_zero_z_and_reads_healthy(self) -> None:
        report = compute_feature_drift(
            live_values={"close": 100.0},
            normalization=[stat("close", 100.0, 10.0)],
        )
        assert report.status == "healthy"
        assert report.z_scores["close"] == 0.0

    def test_no_normalization_at_all_reads_unavailable_not_healthy(self) -> None:
        """A job trained with normalize_features=False carries nothing to
        compare against — reporting 'healthy' would claim a confidence this
        check does not have."""
        report = compute_feature_drift(live_values={"close": 100.0}, normalization=None)
        assert report.status == "unavailable"
        assert report.worst_feature is None
        assert report.worst_z is None
        assert report.z_scores == {}

    def test_an_empty_normalization_list_also_reads_unavailable(self) -> None:
        report = compute_feature_drift(live_values={"close": 100.0}, normalization=[])
        assert report.status == "unavailable"

    def test_a_column_missing_from_live_values_is_skipped_not_an_error(self) -> None:
        report = compute_feature_drift(
            live_values={"close": 100.0},
            normalization=[stat("close", 100.0, 10.0), stat("volume", 50.0, 5.0)],
        )
        assert report.status == "healthy"
        assert set(report.z_scores) == {"close"}

    def test_a_column_missing_from_normalization_is_skipped_not_an_error(self) -> None:
        report = compute_feature_drift(
            live_values={"close": 100.0, "open": 200.0},
            normalization=[stat("close", 100.0, 10.0)],
        )
        assert set(report.z_scores) == {"close"}

    def test_a_zero_std_constant_column_is_skipped_never_a_division_by_zero(self) -> None:
        report = compute_feature_drift(
            live_values={"close": 100.0, "volume": 999999.0},
            normalization=[stat("close", 100.0, 10.0), stat("volume", 100.0, 0.0)],
        )
        assert "volume" not in report.z_scores
        assert report.status == "healthy"

    def test_a_missing_std_is_also_skipped(self) -> None:
        report = compute_feature_drift(
            live_values={"close": 100.0, "volume": 999999.0},
            normalization=[
                stat("close", 100.0, 10.0),
                {"column": "volume", "mean": 100.0, "std": None, "minimum": None, "maximum": None},
            ],
        )
        assert "volume" not in report.z_scores

    def test_status_is_reported_only_if_every_comparable_column_was_skipped(self) -> None:
        """Every column present is a constant (std=0) — nothing genuinely
        comparable, so this is 'unavailable', not a false 'healthy'."""
        report = compute_feature_drift(
            live_values={"volume": 999999.0},
            normalization=[stat("volume", 100.0, 0.0)],
        )
        assert report.status == "unavailable"

    @pytest.mark.parametrize(
        ("z", "expected_status"),
        [
            (DRIFT_Z_THRESHOLD - 0.01, "healthy"),
            (DRIFT_Z_THRESHOLD, "drifted"),
            (DRIFT_Z_THRESHOLD + 0.01, "drifted"),
        ],
    )
    def test_the_threshold_boundary_is_inclusive(self, z: float, expected_status: str) -> None:
        mean, std = 100.0, 10.0
        report = compute_feature_drift(
            live_values={"close": mean + z * std},
            normalization=[stat("close", mean, std)],
        )
        assert report.status == expected_status

    def test_a_severely_negative_z_is_exactly_as_drifted_as_a_positive_one(self) -> None:
        report = compute_feature_drift(
            live_values={"close": -100.0},
            normalization=[stat("close", 100.0, 10.0)],
        )
        assert report.status == "drifted"
        assert report.worst_z == pytest.approx(-20.0)

    def test_the_worst_feature_is_the_largest_magnitude_not_the_largest_signed_value(self) -> None:
        report = compute_feature_drift(
            live_values={"a": 150.0, "b": 40.0},
            normalization=[stat("a", 100.0, 10.0), stat("b", 100.0, 10.0)],
        )
        # a: z=+5, b: z=-6 -> b has the larger magnitude despite the smaller signed value.
        assert report.worst_feature == "b"
        assert report.worst_z == pytest.approx(-6.0)
