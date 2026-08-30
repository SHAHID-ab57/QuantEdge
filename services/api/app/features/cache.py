"""A bounded in-process cache for feature generator results.

Mirrors ``app/indicators/cache.py`` exactly — same bounded-LRU-dict shape,
same fingerprint-the-candles-not-the-query-range identity, same
deliberately-not-Redis-backed rationale (``redis`` remains a declared,
unwired dependency; see ``CLAUDE.md`` § "Known Limitations"). ``fingerprint_candles``
is imported, not redeclared: a candle range's identity is one concept, used
by both caches, and a second copy of that arithmetic would be a guaranteed
source of drift between them.

This exists alongside, not instead of, the indicator engine's own cache.
``app/features/pipeline.py`` previously (and correctly) rejected caching a
*whole dataset* — the memory cost is proportional to the requested range and
the real cost is the candle load, which a dataset-level cache cannot avoid
either. This cache is scoped to one generator's own output for one candle
range and parameter set — the same seam ``IndicatorEngine`` already caches
at — so it helps exactly the case a dataset cache could not: a repeated
identical request (a UI re-render, a sweep revisiting the same window)
recomputing the same generator twice within one dataset build, or across two
different builds that happen to share a feature/params/range. Indicator-backed
features (``sma``/``ema``/``wma``) already get this for free from the shared
``IndicatorEngine`` cache; this is what gives the same benefit to
``ohlcv``/``candle_shape`` and any future non-indicator-backed generator.
"""

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.features.base import FeatureOutput, OHLCVPoint
from app.indicators.cache import fingerprint_candles

__all__ = ["DEFAULT_CACHE_SIZE", "FeatureCache", "FeatureCacheKey", "build_feature_cache_key"]

DEFAULT_CACHE_SIZE = 256


@dataclass(frozen=True, slots=True)
class FeatureCacheKey:
    """Identity of one feature-generator computation — see ``CacheKey`` for
    the identical rationale, applied to a feature name instead of an
    indicator name."""

    feature: str
    params: tuple[tuple[str, Any], ...]
    fingerprint: tuple[int, float, float, float]


def build_feature_cache_key(
    feature: str,
    params: Mapping[str, Any],
    candles: Sequence[OHLCVPoint],
) -> FeatureCacheKey:
    """Build the cache key for one feature generator run."""
    return FeatureCacheKey(
        feature=feature,
        params=tuple(sorted(params.items())),
        fingerprint=fingerprint_candles(candles),
    )


class FeatureCache:
    """A bounded LRU cache of computed feature generator outputs.

    Not thread-safe by design — the same single-threaded-event-loop
    assumption ``IndicatorCache`` documents applies here identically.
    """

    def __init__(self, max_entries: int = DEFAULT_CACHE_SIZE) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[FeatureCacheKey, FeatureOutput] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: FeatureCacheKey) -> FeatureOutput | None:
        """Return a cached result, marking it most-recently-used."""
        output = self._entries.get(key)
        if output is None:
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return output

    def put(self, key: FeatureCacheKey, output: FeatureOutput) -> None:
        """Store a result, evicting the least-recently-used entry if full."""
        self._entries[key] = output
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """Drop every entry and reset the hit/miss counters."""
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        """Hit/miss/size counters, surfaced on ``/system/metrics``-style reads."""
        return {"hits": self._hits, "misses": self._misses, "entries": len(self._entries)}

    def __len__(self) -> int:
        return len(self._entries)
