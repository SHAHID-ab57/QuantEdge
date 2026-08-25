import { z } from 'zod';

/**
 * Wire schemas for the dataset validation API (see
 * `services/api/app/api/v1/endpoints/dataset_validation.py`). Every
 * response is validated against these before the app trusts it, matching
 * the same convention as `features.ts` and `indicators.ts`.
 */

export const ValidationIssueSchema = z.object({
  rule: z.string(),
  category: z.string(),
  severity: z.enum(['error', 'warning', 'info']),
  code: z.string(),
  message: z.string(),
  column: z.string().nullable().optional(),
  row_index: z.number().int().nullable().optional(),
  count: z.number().int().nullable().optional(),
  details: z.record(z.string(), z.unknown()).optional(),
});

export type ValidationIssue = z.infer<typeof ValidationIssueSchema>;

export const ValidationSummarySchema = z.object({
  total_checks: z.number().int().nonnegative(),
  errors: z.number().int().nonnegative(),
  warnings: z.number().int().nonnegative(),
  info: z.number().int().nonnegative(),
});

export type ValidationSummary = z.infer<typeof ValidationSummarySchema>;

export const CategorySummarySchema = z.object({
  errors: z.number().int().nonnegative(),
  warnings: z.number().int().nonnegative(),
  info: z.number().int().nonnegative(),
});

export type CategorySummary = z.infer<typeof CategorySummarySchema>;

/**
 * The outcome of validating one dataset. `passed` is false only when at
 * least one `error`-severity issue was found — a `warning`/`info` issue is
 * always reported but never fails the gate.
 */
export const ValidationReportSchema = z.object({
  dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  engine_version: z.string(),
  validated_at: z.string().datetime(),
  passed: z.boolean(),
  rules_run: z.array(z.string()),
  summary: ValidationSummarySchema,
  categories: z.record(z.string(), CategorySummarySchema),
  issues: z.array(ValidationIssueSchema),
  rows: z.number().int().nonnegative(),
  columns: z.number().int().nonnegative(),
  duration_ms: z.number(),
});

export type ValidationReport = z.infer<typeof ValidationReportSchema>;

export const ValidationRuleSchema = z.object({
  name: z.string(),
  category: z.string(),
  description: z.string(),
  default_severity: z.enum(['error', 'warning', 'info']),
  version: z.string(),
});

export type ValidationRule = z.infer<typeof ValidationRuleSchema>;

export const ValidationRuleCatalogSchema = z.object({
  rules: z.array(ValidationRuleSchema),
  total: z.number().int().nonnegative(),
  categories: z.array(z.string()),
});

export type ValidationRuleCatalog = z.infer<typeof ValidationRuleCatalogSchema>;
