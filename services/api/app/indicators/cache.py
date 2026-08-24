"""A bounded in-process cache for indicator results.

**What this does and does not buy you.** The cache key includes a
fingerprint of the input candles, which the caller can only produce *after*
reading them from the database — so a hit saves the recomputation, never
the query. That is deliberate and worth stating plainly: for a 20-period
SMA over a few hundred candles the saving is negligible, and the honest
answer is that the database read dominates. It becomes worthwhile for
genuinely expensive indicators and for repeated identical requests (a UI
re-rendering the same parameters, or a sweep that revisits the same
window), which is exactly the traffic shape a research dashboard produces.

It is deliberately *not* Redis-backed. ``redis`` is a declared dependency
with no wired usage anywhere in this codebase yet (see ``CLAUDE.md`` §
"Known Limitations"); introducing the platform's first Redis dependency for
a cache whose main cost is a database read it cannot avoid would be the
wrong trade. This is a plain in-process dict with an LRU bound, and the
seam to swap it for a shared cache later is a single ``IndicatorCache``
protocol.
"""

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.indicators.base import IndicatorOutput, OHLCVPoint

DEFAULT_CACHE_SIZE = 256


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Identity of one indicator computation.

    ``fingerprint`` stands in for the candle contents. Closed historical
    candles are immutable, so ``(count, first open, last open, last close)``
    distinguishes any two ranges a caller could realistically pass — and
    including the *last close* is what catches the one genuinely mutable
    case, a still-forming final candle whose close keeps changing while its
    open time does not.
    """

    indicator: str
    params: tuple[tuple[str, Any], ...]
    fingerprint: tuple[int, float, float, float]


def fingerprint_candles(candles: Sequence[OHLCVPoint]) -> tuple[int, float, float, float]:
    """Summarize a candle range in O(1) for use in a cache key."""
    if not candles:
        return (0, 0.0, 0.0, 0.0)
    first = candles[0]
    last = candles[-1]
    return (
        len(candles),
        first.open_time.timestamp(),
        last.open_time.timestamp(),
        last.close,
    )


def build_cache_key(
    indicator: str,
    params: Mapping[str, Any],
    candles: Sequence[OHLCVPoint],
) -> CacheKey:
    """Build the cache key for one indicator run."""
    return CacheKey(
        indicator=indicator,
        params=tuple(sorted(params.items())),
        fingerprint=fingerprint_candles(candles),
    )


class IndicatorCache:
    """A bounded LRU cache of computed indicator outputs.

    Not thread-safe by design: FastAPI runs these calculations on the event
    loop, so every access is already serialized by the single-threaded
    loop — the same assumption ``MarketStateManager`` documents for its own
    in-memory state.
    """

    def __init__(self, max_entries: int = DEFAULT_CACHE_SIZE) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[CacheKey, IndicatorOutput] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: CacheKey) -> IndicatorOutput | None:
        """Return a cached result, marking it most-recently-used."""
        output = self._entries.get(key)
        if output is None:
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return output

    def put(self, key: CacheKey, output: IndicatorOutput) -> None:
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
