import { describe, expect, it } from 'vitest';
import { ConnectorSchema } from './connectors';

const base = {
  source: 'fear_greed',
  label: 'Fear & Greed Index',
  description: 'A daily sentiment index.',
  frequency: 'daily',
  requires_auth: false,
  latest_value: 42,
  latest_timestamp: '2026-01-02T00:00:00Z',
  expected_interval_seconds: 86_400,
  total_points: 120,
  last_attempt_at: '2026-01-02T00:05:00Z',
  last_attempt_success: true,
  next_sync_at: '2026-01-03T00:05:00Z',
};

describe('ConnectorSchema — health_status', () => {
  it.each(['healthy', 'stale', 'failing', 'never_ingested'] as const)(
    'accepts the backend health status %s',
    (health_status) => {
      expect(ConnectorSchema.parse({ ...base, health_status }).health_status).toBe(health_status);
    },
  );

  it('rejects a status the backend does not define', () => {
    expect(() => ConnectorSchema.parse({ ...base, health_status: 'degraded' })).toThrow();
  });

  it('requires the field, so a backend that stops sending it fails loudly', () => {
    expect(() => ConnectorSchema.parse(base)).toThrow();
  });
});

describe('ConnectorSchema — sync-timing fields', () => {
  const valid = { ...base, health_status: 'healthy' as const };

  it('accepts null last_attempt_at/last_attempt_success/next_sync_at together — no attempt on record', () => {
    const parsed = ConnectorSchema.parse({
      ...valid,
      last_attempt_at: null,
      last_attempt_success: null,
      next_sync_at: null,
    });
    expect(parsed.last_attempt_at).toBeNull();
    expect(parsed.next_sync_at).toBeNull();
  });

  it('requires expected_interval_seconds and total_points, so a backend regression fails loudly', () => {
    expect(() =>
      ConnectorSchema.parse({ ...valid, expected_interval_seconds: undefined }),
    ).toThrow();
    expect(() => ConnectorSchema.parse({ ...valid, total_points: undefined })).toThrow();
  });

  it('rejects a non-ISO next_sync_at, the same strictness as latest_timestamp', () => {
    expect(() => ConnectorSchema.parse({ ...valid, next_sync_at: 'not-a-date' })).toThrow();
  });
});
