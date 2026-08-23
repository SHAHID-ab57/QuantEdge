import { ONE_MINUTE_MS } from './rolling-window';
import type { TradeRecord } from './trade-record';

/**
 * A histogram of recent trade sizes, bucketed _relative to the window's own
 * average trade size_ rather than by absolute quantity. Relative bucketing
 * is what makes this readable across wildly different markets without any
 * per-symbol configuration: "most trades are under half the average size,
 * with a thin tail of 5×+ prints" means the same thing on a $2 asset and a
 * $70,000 one, whereas fixed absolute buckets would be meaningless on one
 * of them.
 *
 * Reading it: a distribution concentrated in the small buckets is retail-
 * sized flow; a fat right tail means a few large prints are moving most of
 * the volume, which is exactly the situation where the average trade size
 * on its own is misleading.
 */
export interface SizeBucket {
  /** Short axis label, e.g. `"0.5–1×"`. */
  label: string;
  /** Inclusive lower bound as a multiple of average size. */
  minMultiple: number;
  /** Exclusive upper bound, or `null` for the open-ended top bucket. */
  maxMultiple: number | null;
  count: number;
  /** `count / total`, in [0, 1]; `0` when the window is empty. */
  share: number;
}

export interface SizeDistribution {
  buckets: SizeBucket[];
  /** Number of trades in the window this distribution covers. */
  total: number;
  /** The average size the bucket boundaries are relative to, or `null` if the window is empty. */
  averageSize: number | null;
}

/** Bucket edges as multiples of the window's average trade size. */
const BUCKET_EDGES: { label: string; min: number; max: number | null }[] = [
  { label: '<0.5×', min: 0, max: 0.5 },
  { label: '0.5–1×', min: 0.5, max: 1 },
  { label: '1–2×', min: 1, max: 2 },
  { label: '2–5×', min: 2, max: 5 },
  { label: '≥5×', min: 5, max: null },
];

function emptyBuckets(): SizeBucket[] {
  return BUCKET_EDGES.map((edge) => ({
    label: edge.label,
    minMultiple: edge.min,
    maxMultiple: edge.max,
    count: 0,
    share: 0,
  }));
}

/**
 * `records` need not be pre-pruned — this filters to `windowMs` (default one
 * minute, matching the rest of the dashboard's rolling figures) itself.
 */
export function computeSizeDistribution(
  records: readonly TradeRecord[],
  nowMs: number,
  windowMs: number = ONE_MINUTE_MS,
): SizeDistribution {
  const cutoff = nowMs - windowMs;
  const window = records.filter((record) => record.timestampMs >= cutoff);
  const buckets = emptyBuckets();
  if (window.length === 0) {
    return { buckets, total: 0, averageSize: null };
  }

  let totalSize = 0;
  for (const record of window) {
    totalSize += record.size;
  }
  const averageSize = totalSize / window.length;
  if (averageSize <= 0) {
    // Every trade had zero size — nothing meaningful to bucket by, and
    // dividing by it below would produce NaN/Infinity multiples.
    return { buckets, total: window.length, averageSize };
  }

  for (const record of window) {
    const multiple = record.size / averageSize;
    // The last bucket is open-ended, so a trade can always be placed.
    const index = BUCKET_EDGES.findIndex(
      (edge) => multiple >= edge.min && (edge.max === null || multiple < edge.max),
    );
    const bucket = buckets[index === -1 ? buckets.length - 1 : index];
    if (bucket) {
      bucket.count += 1;
    }
  }

  for (const bucket of buckets) {
    bucket.share = bucket.count / window.length;
  }

  return { buckets, total: window.length, averageSize };
}
