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

  const volume = volumePoints(totalCandles);

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

export type QualityStatus = 'pass' | 'warn' | 'fail';

export interface QualityBreakdownItem {
  id: string;
  label: string;
  points: number;
  max: number;
  status: QualityStatus;
  detail: string;
}

function freshnessFactor(ageSeconds: number): {
  points: number;
  status: QualityStatus;
  detail: string;
} {
  if (ageSeconds < 3_600) {
    return { points: 50, status: 'pass', detail: 'Latest candle is current' };
  }
  if (ageSeconds < 86_400) {
    return { points: 40, status: 'warn', detail: 'Latest candle is within the last 24 hours' };
  }
  if (ageSeconds < 7 * 86_400) {
    return { points: 25, status: 'fail', detail: 'Latest candle is more than a day old' };
  }
  if (ageSeconds < 30 * 86_400) {
    return { points: 10, status: 'fail', detail: 'Latest candle is more than a week old' };
  }
  return { points: 0, status: 'fail', detail: 'Latest candle is more than a month old' };
}

function volumePoints(totalCandles: number): number {
  if (totalCandles >= 100_000) {
    return 20;
  }
  if (totalCandles >= 10_000) {
    return 15;
  }
  if (totalCandles >= 1_000) {
    return 10;
  }
  if (totalCandles >= 100) {
    return 5;
  }
  return 0;
}

function volumeFactor(totalCandles: number): {
  points: number;
  status: QualityStatus;
  detail: string;
} {
  if (totalCandles >= 100_000) {
    return { points: 20, status: 'pass', detail: 'More than 100,000 candles stored' };
  }
  if (totalCandles >= 10_000) {
    return { points: 15, status: 'warn', detail: 'More than 10,000 candles stored' };
  }
  if (totalCandles >= 1_000) {
    return { points: 10, status: 'warn', detail: 'More than 1,000 candles stored' };
  }
  if (totalCandles >= 100) {
    return { points: 5, status: 'warn', detail: 'More than 100 candles stored' };
  }
  return { points: 0, status: 'fail', detail: 'Fewer than 100 candles stored' };
}

export function qualityBreakdown(input: QualityInput): QualityBreakdownItem[] {
  const ageSeconds = input.lastSyncAt
    ? Math.max(0, (input.now - new Date(input.lastSyncAt).getTime()) / 1000)
    : null;

  const freshness =
    ageSeconds !== null
      ? freshnessFactor(ageSeconds)
      : { points: 0, status: 'fail' as const, detail: 'No stored candles yet' };

  const known = new Set(KNOWN_TIMEFRAMES);
  const covered = input.timeframes.filter((tf) => known.has(tf)).length;
  const coveragePoints = Math.round(30 * (covered / KNOWN_TIMEFRAMES.length));
  let coverageStatus: QualityStatus;
  if (covered === KNOWN_TIMEFRAMES.length) {
    coverageStatus = 'pass';
  } else if (covered > 0) {
    coverageStatus = 'warn';
  } else {
    coverageStatus = 'fail';
  }
  const coverageDetail =
    covered === KNOWN_TIMEFRAMES.length
      ? `All ${KNOWN_TIMEFRAMES.length} standard timeframes synced`
      : `${covered} of ${KNOWN_TIMEFRAMES.length} standard timeframes synced`;

  const volume = volumeFactor(input.totalCandles);

  return [
    {
      id: 'freshness',
      label: 'Latest candle freshness',
      points: freshness.points,
      max: 50,
      status: freshness.status,
      detail: freshness.detail,
    },
    {
      id: 'coverage',
      label: 'Timeframe coverage',
      points: coveragePoints,
      max: 30,
      status: coverageStatus,
      detail: coverageDetail,
    },
    {
      id: 'volume',
      label: 'Stored candle volume',
      points: volume.points,
      max: 20,
      status: volume.status,
      detail: volume.detail,
    },
  ].filter((item) => item.points > 0 || item.status === 'fail');
}

export function qualityRecommendations(input: QualityInput): string[] {
  const recommendations: string[] = [];

  const ageSeconds = input.lastSyncAt
    ? Math.max(0, (input.now - new Date(input.lastSyncAt).getTime()) / 1000)
    : null;
  if (ageSeconds === null) {
    recommendations.push('Synchronize historical candles to create the first data set');
  } else if (ageSeconds >= 3_600) {
    const hours = Math.floor(ageSeconds / 3_600);
    recommendations.push(
      `Latest candle is ${hours}h old — ensure the candle sync scheduler is running`,
    );
  }

  const missing = KNOWN_TIMEFRAMES.filter((tf) => !input.timeframes.includes(tf));
  if (missing.length > 0) {
    recommendations.push(`Enable additional timeframes: ${missing.join(', ')}`);
  }

  if (input.totalCandles < 1_000) {
    recommendations.push('Synchronize additional historical candles (backfill)');
  }

  if (
    ageSeconds !== null &&
    ageSeconds < 3_600 &&
    missing.length === 0 &&
    input.totalCandles >= 1_000
  ) {
    recommendations.push('Data is current and complete');
  }

  return recommendations;
}

export const QUALITY_BREAKDOWN =
  'Data quality score (0–100): latest candle freshness (50 pts), timeframe coverage of the standard set (30 pts), and total stored candle volume (20 pts).';
