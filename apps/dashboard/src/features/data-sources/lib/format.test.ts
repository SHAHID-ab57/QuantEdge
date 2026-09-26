import { describe, expect, it } from 'vitest';
import {
  formatConnectorValue,
  formatConnectorValueExact,
  formatInterval,
  formatLastAttempt,
  formatLastUpdated,
  formatNextSync,
} from './format';

describe('formatInterval', () => {
  it('renders a whole-day cadence in days', () => {
    expect(formatInterval(86_400)).toBe('every 1d');
  });

  it('renders funding rate’s 8-hour cadence in hours, not a fraction of a day', () => {
    expect(formatInterval(28_800)).toBe('every 8h');
  });

  it('renders an hourly cadence', () => {
    expect(formatInterval(3_600)).toBe('every 1h');
  });
});

describe('formatConnectorValue', () => {
  it('shows Unavailable for a connector never ingested', () => {
    expect(formatConnectorValue(null)).toBe('Unavailable');
  });

  it('shows a bare zero, never a misleadingly empty string', () => {
    expect(formatConnectorValue(0)).toBe('0');
  });

  it('does not round a small fraction down to zero — the funding-rate bug', () => {
    // 0.0001 = 0.01% per 8h (ETHUSD Funding Rate); two fixed decimal places
    // used to round this to "0.00" -> "0", indistinguishable from a
    // genuinely zero rate.
    expect(formatConnectorValue(0.0001)).toBe('0.0001');
  });

  it('shows more precision than two fixed decimals for a sub-1 value', () => {
    expect(formatConnectorValue(0.320904733)).toBe('0.3209');
  });

  it('keeps thousands separators and two decimals for a large value', () => {
    expect(formatConnectorValue(16_119.62)).toBe('16,119.62');
  });

  it('does not spill float noise for a very large value', () => {
    // Grouping (thousands vs. lakh/crore) is locale-dependent in the test
    // environment — what matters here is the decimal precision, not which
    // digit-grouping convention renders it.
    expect(formatConnectorValue(54_284_255_476.391)).toMatch(/^54,?\d[\d,]*\.39$/);
  });

  it('trims a trailing zero for an exact fixture value', () => {
    expect(formatConnectorValue(42)).toBe('42');
    expect(formatConnectorValue(-0.12)).toBe('-0.12');
  });

  it('preserves the sign of a negative small value', () => {
    expect(formatConnectorValue(-0.0001)).toBe('-0.0001');
  });
});

describe('formatConnectorValueExact', () => {
  it('shows Unavailable for null', () => {
    expect(formatConnectorValueExact(null)).toBe('Unavailable');
  });

  it('does not truncate a value formatConnectorValue would round', () => {
    expect(formatConnectorValueExact(58.90169835250921)).toContain('58.9016983525');
  });
});

describe('formatLastUpdated', () => {
  const now = new Date('2026-09-22T12:00:00Z').getTime();

  it('reports no data yet for a never-ingested connector', () => {
    expect(formatLastUpdated(null, now)).toBe('No data yet');
  });

  it('reports just now for a value from moments ago', () => {
    expect(formatLastUpdated('2026-09-22T11:59:50Z', now)).toBe('just now');
  });

  it('reports a relative age in the coarsest legible unit', () => {
    expect(formatLastUpdated('2026-09-22T11:55:00Z', now)).toBe('5m ago');
    expect(formatLastUpdated('2026-09-22T09:00:00Z', now)).toBe('3h ago');
    expect(formatLastUpdated('2026-09-20T12:00:00Z', now)).toBe('2d ago');
  });
});

describe('formatLastAttempt', () => {
  const now = new Date('2026-09-22T12:00:00Z').getTime();

  it('reports no attempt recorded when the scheduler has never touched this source', () => {
    expect(formatLastAttempt(null, null, now)).toEqual({ label: 'No sync attempted yet' });
  });

  it('reports a successful fetch with its age', () => {
    expect(formatLastAttempt('2026-09-22T11:57:00Z', true, now)).toEqual({
      label: 'Fetched 3m ago',
      success: true,
    });
  });

  it('reports a failed fetch distinctly from a successful one', () => {
    expect(formatLastAttempt('2026-09-22T11:57:00Z', false, now)).toEqual({
      label: 'Fetch failed 3m ago',
      success: false,
    });
  });
});

describe('formatNextSync', () => {
  const now = new Date('2026-09-22T12:00:00Z').getTime();

  it('reports awaiting first sync when nothing has ever been attempted', () => {
    expect(formatNextSync(null, now)).toEqual({ label: 'Awaiting first sync', overdue: false });
  });

  it('counts down to a projected future sync', () => {
    expect(formatNextSync('2026-09-22T12:42:00Z', now)).toEqual({
      label: 'Next sync in 42m',
      overdue: false,
    });
  });

  it('reports overdue once the projected time has passed — the real Open Interest bug', () => {
    // The scheduler's own gap this page needs to explain, not hide: a
    // connector whose last attempt was hours before its own interval elapsed
    // is not "just quiet," it is a stalled tick.
    expect(formatNextSync('2026-09-22T08:00:00Z', now)).toEqual({
      label: 'Next sync overdue by 4h',
      overdue: true,
    });
  });
});
