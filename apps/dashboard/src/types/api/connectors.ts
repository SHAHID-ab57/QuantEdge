import { z } from 'zod';

/**
 * Wire schemas for the External Data Connectors read API (see
 * `services/api/app/schemas/connectors.py`). Every response is validated
 * against these before the app trusts it, matching the same convention
 * as `market.ts` and `features.ts`.
 */

export const ConnectorSchema = z.object({
  source: z.string(),
  label: z.string(),
  description: z.string(),
  frequency: z.string(),
  requires_auth: z.boolean(),
  /** Null when this connector is registered but has never been ingested. */
  latest_value: z.number().nullable(),
  latest_timestamp: z.string().datetime().nullable(),
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
