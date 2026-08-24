import { z } from 'zod';

/**
 * Wire schemas for the technical indicator API (see
 * `services/api/app/api/v1/endpoints/indicators.py`). Every response is
 * validated against these before the app trusts it, matching the same
 * convention as `market.ts`.
 */

export const IndicatorParameterTypeSchema = z.enum(['int', 'float', 'string', 'bool']);

export type IndicatorParameterType = z.infer<typeof IndicatorParameterTypeSchema>;

/**
 * One parameter an indicator accepts. The backend publishes the full
 * constraint set (type, bounds, choices, default) precisely so the
 * parameter form can be generated from data rather than hardcoded
 * per-indicator on this side — adding an indicator to the backend must not
 * require a frontend change.
 */
export const IndicatorParameterSpecSchema = z.object({
  name: z.string(),
  type: IndicatorParameterTypeSchema,
  label: z.string(),
  description: z.string(),
  /** `unknown` because the type varies by `type`; narrowed at the form layer. */
  default: z.unknown().nullable(),
  required: z.boolean(),
  minimum: z.number().nullable(),
  maximum: z.number().nullable(),
  choices: z.array(z.string()),
});

export type IndicatorParameterSpec = z.infer<typeof IndicatorParameterSpecSchema>;

export const IndicatorOutputSpecSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
});

export type IndicatorOutputSpec = z.infer<typeof IndicatorOutputSpecSchema>;

export const IndicatorSchema = z.object({
  name: z.string(),
  label: z.string(),
  description: z.string(),
  category: z.string(),
  parameters: z.array(IndicatorParameterSpecSchema),
  outputs: z.array(IndicatorOutputSpecSchema),
  /** Indicator-level semver, independent of the platform's own release version. */
  version: z.string(),
  author: z.string(),
  /** Free-form Big-O / performance note. */
  complexity: z.string(),
  /** How the warmup candle count relates to this indicator's parameters. */
  warmup_description: z.string(),
  /**
   * Alternate names a search should also match, e.g. "MA" for "sma".
   * Optional (rather than defaulted) so existing fixtures/tests built
   * before this field existed keep compiling unchanged; read as
   * `indicator.aliases ?? []`.
   */
  aliases: z.array(z.string()).optional(),
});

export type Indicator = z.infer<typeof IndicatorSchema>;

export const IndicatorCatalogSchema = z.object({
  indicators: z.array(IndicatorSchema),
  total: z.number().int().nonnegative(),
  categories: z.array(z.string()),
});

export type IndicatorCatalog = z.infer<typeof IndicatorCatalogSchema>;

/**
 * One computed series. `values` aligns index-for-index with the response's
 * `timestamps`; `null` marks a warmup position where the indicator is not
 * yet defined — never a failure, which arrives as an error response.
 */
export const IndicatorSeriesSchema = z.object({
  name: z.string(),
  label: z.string(),
  values: z.array(z.number().nullable()),
});

export type IndicatorSeries = z.infer<typeof IndicatorSeriesSchema>;

export const IndicatorCalculationMetaSchema = z.object({
  candles_analyzed: z.number().int().nonnegative(),
  warmup_candles: z.number().int().nonnegative(),
  execution_time_ms: z.number(),
  database_time_ms: z.number(),
  cache_status: z.string(),
  generated_at: z.string().datetime(),
});

export type IndicatorCalculationMeta = z.infer<typeof IndicatorCalculationMetaSchema>;

export const IndicatorCalculationSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  indicator: IndicatorSchema,
  /** The fully-resolved parameters actually used, including applied defaults. */
  parameters: z.record(z.string(), z.unknown()),
  timestamps: z.array(z.string().datetime()),
  series: z.array(IndicatorSeriesSchema),
  meta: IndicatorCalculationMetaSchema,
});

export type IndicatorCalculation = z.infer<typeof IndicatorCalculationSchema>;

/**
 * One indicator's outcome within a batch — either a result or a domain
 * error, never both. `series`/`cache_status` are present only when
 * `success` is true; `error_code`/`error_detail` only when it's false.
 */
export const IndicatorBatchItemResultSchema = z.object({
  indicator: z.string(),
  success: z.boolean(),
  label: z.string().nullable(),
  parameters: z.record(z.string(), z.unknown()).nullable(),
  series: z.array(IndicatorSeriesSchema).nullable(),
  cache_status: z.string().nullable(),
  /** Present only when `success` is true. */
  warmup_candles: z.number().int().nonnegative().nullable(),
  /** This item's own indicator calculation time; present only when `success` is true. */
  execution_time_ms: z.number().nullable(),
  error_code: z.string().nullable(),
  error_detail: z.string().nullable(),
});

export type IndicatorBatchItemResult = z.infer<typeof IndicatorBatchItemResultSchema>;

/**
 * Several indicators calculated together over one shared candle load — the
 * chart overlay API. `timestamps` is shared by every successful result
 * rather than repeated per item, since they were all computed over the
 * identical candle range.
 */
export const IndicatorBatchResponseSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  timestamps: z.array(z.string().datetime()),
  results: z.array(IndicatorBatchItemResultSchema),
  /** Candle count shared by every result — one candle load for the whole batch. */
  candles_analyzed: z.number().int().nonnegative(),
  /** Time spent loading candles once for the whole batch. */
  database_time_ms: z.number(),
  /** The execution pipeline's own version, shared by every result. */
  engine_version: z.string(),
  generated_at: z.string().datetime(),
});

export type IndicatorBatchResponse = z.infer<typeof IndicatorBatchResponseSchema>;
