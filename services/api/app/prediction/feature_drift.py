"""Live feature-scale drift detection (FEATURE-DRIFT-MONITOR).

Mirrors `app.connectors.health.compute_health_status` deliberately — same
shape of problem, same answer. That module's own opening paragraph could be
republished here almost verbatim: three real, previously-silent connector
bugs motivated it because nothing on this platform ever asked "how long has
it been since this connector's data actually moved forward?" This module
exists because nothing ever asked the analogous question of a live
prediction: "is what I'm about to act on anywhere near what this model was
actually trained on?"

**The two real incidents this was built for**
(`docs/research/FEATURE_DRIFT_INVESTIGATION.md`), found by checking the live
system directly, not synthetically: training job `733082cc` (two live paper
accounts) had drifted through `volume` — its own live z-score reached +89,
worse than the +58 that first exposed the problem — while job `6e7fb4ed`
(the third live account, retrained only 13 days earlier) had drifted through
**price and SMA(20) instead**, because its 100-candle training window's own
standard deviation was too tight to survive an ordinary two-week move (z =
+15 to +18). Both were producing near-saturated ("down", >99% confidence)
live predictions as a direct, ablation-confirmed result, with nothing on the
platform flagging either condition.

**Where the threshold comes from — real data, not a guess.** A genuinely
healthy reading — the held-out **test split of the same window a job's own
normalization was fit on**, i.e. by construction not drifted — was measured
directly for job `733082cc` (965 real rows): price/SMA columns never exceed
|z| = 2.6, and even `volume`'s own heavier right tail (real hourly volume is
never close to normally distributed) tops out at |z| = 9.32. Both real
drift incidents above measured 15.4 to 89 — one to two orders of magnitude
past that. `DRIFT_Z_THRESHOLD = 10.0` sits with real headroom above the
worst *healthy* reading measured (9.32) and with an enormous margin below
the mildest *real* incident measured (15.4), so it separates the two
cleanly without needing a per-feature tuned value.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "DRIFT_Z_THRESHOLD",
    "FeatureDriftReport",
    "FeatureDriftStatus",
    "compute_feature_drift",
]

FeatureDriftStatus = Literal["healthy", "drifted", "unavailable"]

#: See this module's own docstring for the real, measured numbers behind
#: this choice: a genuinely healthy reading never exceeds 9.32; both real
#: incidents this exists to catch measured 15.4-89.
DRIFT_Z_THRESHOLD = 10.0


@dataclass(frozen=True)
class FeatureDriftReport:
    """One prediction's drift check, against its own job's stored normalization.

    `unavailable` — not `healthy` — when the job carries no normalization
    stats at all (`normalize_features=False`, or a model kind that never
    sets any): there is genuinely nothing to compare against, and reporting
    `healthy` would claim a confidence this check does not have. Mirrors
    `ConnectorHealthStatus.never_ingested`'s own reasoning for the same
    shape of gap.
    """

    status: FeatureDriftStatus
    #: Every feature actually compared, keyed by column name.
    z_scores: dict[str, float]
    #: The single largest-magnitude z-score's own column name, or `None`
    #: when nothing was comparable.
    worst_feature: str | None
    #: That column's own signed z-score (its sign is meaningful: a
    #: severely *negative* z is exactly as drifted as a severely positive
    #: one, `abs()` is what decides status, but the sign is kept for
    #: display — "price is 17 std devs *below* what this model expects" is
    #: a more useful message than a bare magnitude).
    worst_z: float | None


def compute_feature_drift(
    *,
    live_values: Mapping[str, float],
    normalization: Sequence[Mapping[str, Any]] | None,
    threshold: float = DRIFT_Z_THRESHOLD,
) -> FeatureDriftReport:
    """Z-score every live feature against its job's own stored fit, and flag
    the worst one.

    `normalization` is exactly the plain-dict shape
    `app.training.normalization.normalization_stats_to_dicts` produces and
    every real model adapter already persists onto
    `TrainingJob.result_summary["normalization"]` — this function reads
    the *already-stored* fit, it never recomputes or re-estimates one, so
    a call here can never itself look ahead or drift.

    A column present in `live_values` but absent from `normalization` (or
    vice versa), or one whose stored `std` is `0`/missing (a constant
    column — `ColumnNormalizer.fit`'s own convention leaves `std` unset
    rather than dividing by zero), is silently skipped, not an error: this
    is a best-effort safety check over whatever *is* comparable, not a
    strict schema match.
    """
    if not normalization:
        return FeatureDriftReport(
            status="unavailable", z_scores={}, worst_feature=None, worst_z=None
        )

    z_scores: dict[str, float] = {}
    for stat in normalization:
        column = stat.get("column")
        mean = stat.get("mean")
        std = stat.get("std")
        if not isinstance(column, str) or column not in live_values:
            continue
        if mean is None or not std:
            continue
        z_scores[column] = (live_values[column] - mean) / std

    if not z_scores:
        return FeatureDriftReport(
            status="unavailable", z_scores={}, worst_feature=None, worst_z=None
        )

    worst_feature = max(z_scores, key=lambda name: abs(z_scores[name]))
    worst_z = z_scores[worst_feature]
    status: FeatureDriftStatus = "drifted" if abs(worst_z) >= threshold else "healthy"
    return FeatureDriftReport(
        status=status, z_scores=z_scores, worst_feature=worst_feature, worst_z=worst_z
    )
