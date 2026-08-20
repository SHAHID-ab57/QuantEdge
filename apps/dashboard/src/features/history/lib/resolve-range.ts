export const RANGE_PRESETS = ['all', 'today', 'yesterday', '24h', '7d', '30d', 'custom'] as const;

export type RangePreset = (typeof RANGE_PRESETS)[number];

export const RANGE_PRESET_LABELS: Record<RangePreset, string> = {
  all: 'All History',
  today: 'Today',
  yesterday: 'Yesterday',
  '24h': 'Last 24 Hours',
  '7d': 'Last 7 Days',
  '30d': 'Last 30 Days',
  custom: 'Custom Range',
};

export const DAY_MS = 86_400_000;

export interface ResolvedRange {
  start: string | null;
  end: string | null;
}

export function toIsoUtc(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function startOfUtcDay(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

/** Resolve a preset range to half-open UTC bounds, or `null` for all history. */
export function resolveRange(preset: RangePreset, now: Date = new Date()): ResolvedRange {
  if (preset === 'all') {
    return { start: null, end: null };
  }
  if (preset === 'custom') {
    return { start: null, end: null };
  }
  const today = startOfUtcDay(now);
  const end = toIsoUtc(now);
  switch (preset) {
    case 'today':
      return { start: toIsoUtc(today), end };
    case 'yesterday': {
      const start = new Date(today.getTime() - DAY_MS);
      return { start: toIsoUtc(start), end: toIsoUtc(today) };
    }
    case '24h': {
      const start = new Date(now.getTime() - DAY_MS);
      return { start: toIsoUtc(start), end };
    }
    case '7d': {
      const start = new Date(today.getTime() - 6 * DAY_MS);
      return { start: toIsoUtc(start), end };
    }
    case '30d': {
      const start = new Date(today.getTime() - 29 * DAY_MS);
      return { start: toIsoUtc(start), end };
    }
    default:
      return { start: null, end: null };
  }
}

export function isRangePreset(value: string | null): value is RangePreset {
  return value !== null && (RANGE_PRESETS as readonly string[]).includes(value);
}
