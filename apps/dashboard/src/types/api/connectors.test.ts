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
