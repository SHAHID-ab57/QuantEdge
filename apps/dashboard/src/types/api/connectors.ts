import { z } from 'zod';

/**
 * Wire schemas for the External Data Connectors read API (see
 * `services/api/app/schemas/connectors.py`). Every response is validated
 * against these before the app trusts it, matching the same convention
 * as `market.ts` and `features.ts`.
 */

/**
 * 'healthy': a new point has arrived within this source's own expected
 * cadence. 'stale': it hasn't (see `services/api/app/connectors/health.py`).
 * 'failing': its most recent sync attempts all errored, even if its last
 * good point is still recent. 'never_ingested': no point has ever been
 * stored.
 */
export const ConnectorHealthStatusSchema = z.enum([
  'healthy',
  'stale',
  'failing',
  'never_ingested',
]);

export type ConnectorHealthStatus = z.infer<typeof ConnectorHealthStatusSchema>;

export const ConnectorSchema = z.object({
  source: z.string(),
  label: z.string(),
  description: z.string(),
  frequency: z.string(),
  requires_auth: z.boolean(),
  /** Null when this connector is registered but has never been ingested. */
  latest_value: z.number().nullable(),
  latest_timestamp: z.string().datetime().nullable(),
  health_status: ConnectorHealthStatusSchema,
  /** This source's own real cadence — what 'stale' is measured against. */
  expected_interval_seconds: z.number().int().positive(),
  /** Every point ever stored for this source. */
  total_points: z.number().int().nonnegative(),
  /** When the owning scheduler last actually tried this source — success or
   * failure, and distinct from `latest_timestamp` (an attempt can find
   * nothing new to store). Null if no attempt has ever been recorded. */
  last_attempt_at: z.string().datetime().nullable(),
  /** Null exactly when `last_attempt_at` is null. */
  last_attempt_success: z.boolean().nullable(),
  /** The most recent sync attempt's own error message, when it failed.
   * Null on success or when no attempt has been recorded. */
  last_attempt_error: z.string().nullable(),
  /** `last_attempt_at` plus the owning scheduler's tick interval — an
   * estimate. In the past means a tick is overdue. Null with no attempt on
   * record yet. */
  next_sync_at: z.string().datetime().nullable(),
  /** A plain-English reason for a non-healthy status — distinguishes a
   * scheduler that stopped ticking from one still ticking against a
   * source with nothing new to report, and names a real sync error.
   * Null for 'healthy'. */
  health_reason: z.string().nullable(),
});

export type Connector = z.infer<typeof ConnectorSchema>;

export const ConnectorCatalogSchema = z.object({
  connectors: z.array(ConnectorSchema),
  total: z.number().int().nonnegative(),
});

export type ConnectorCatalog = z.infer<typeof ConnectorCatalogSchema>;

export const ExternalDataPointSchema = z.object({
  timestamp: z.string().datetime(),
  value: z.number(),
});

export type ExternalDataPoint = z.infer<typeof ExternalDataPointSchema>;

export const ConnectorHistoryPaginationSchema = z.object({
  total: z.number().int().nonnegative(),
  returned: z.number().int().nonnegative(),
  has_more: z.boolean(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export const ConnectorHistorySchema = z.object({
  source: z.string(),
  items: z.array(ExternalDataPointSchema),
  pagination: ConnectorHistoryPaginationSchema,
});

export type ConnectorHistory = z.infer<typeof ConnectorHistorySchema>;
