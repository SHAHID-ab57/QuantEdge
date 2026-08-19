const KNOWN_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'];

export interface QualityInput {
  timeframes: string[];
  totalCandles: number;
  lastSyncAt: string | null;
  now: number;
}

export type QualityLabel = 'Good' | 'Fair' | 'Poor';

export function computeQualityScore({
  timeframes,
  totalCandles,
  lastSyncAt,
  now,
}: QualityInput): number {
  let freshness = 0;
  if (lastSyncAt) {
    const ageSeconds = Math.max(0, (now - new Date(lastSyncAt).getTime()) / 1000);
    if (ageSeconds < 3_600) {
      freshness = 50;
    } else if (ageSeconds < 86_400) {
      freshness = 40;
    } else if (ageSeconds < 7 * 86_400) {
      freshness = 25;
    } else if (ageSeconds < 30 * 86_400) {
      freshness = 10;
    }
  }

  const known = new Set(KNOWN_TIMEFRAMES);
  const covered = timeframes.filter((tf) => known.has(tf)).length;
  const coverage = Math.round(30 * (covered / KNOWN_TIMEFRAMES.length));

  let volume = 0;
  if (totalCandles >= 100_000) {
    volume = 20;
  } else if (totalCandles >= 10_000) {
    volume = 15;
  } else if (totalCandles >= 1_000) {
    volume = 10;
  } else if (totalCandles >= 100) {
    volume = 5;
  }

  return Math.min(100, freshness + coverage + volume);
}

export function qualityLabel(score: number): QualityLabel {
  if (score >= 80) {
    return 'Good';
  }
  if (score >= 50) {
    return 'Fair';
  }
  return 'Poor';
}

export const QUALITY_BREAKDOWN =
  'Data quality score (0–100): latest candle freshness (50 pts), timeframe coverage of the standard set (30 pts), and total stored candle volume (20 pts).';
