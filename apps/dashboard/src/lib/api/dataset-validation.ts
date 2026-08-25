import { apiClient } from './client';
import type { BuildDatasetParams } from './features';
import {
  ValidationReportSchema,
  ValidationRuleCatalogSchema,
  type ValidationReport,
  type ValidationRuleCatalog,
} from '@/types/api/dataset-validation';

/**
 * The dataset-validation-only additions to a dataset build request:
 * `required_columns` (columns that must exist beyond what the selected
 * features imply) and `rules` (run only this subset; omit to run every
 * registered rule). Extending `BuildDatasetParams` rather than duplicating
 * its fields is what lets the exact same market/timeframe/range/feature
 * selection that builds a dataset also validate it.
 */
export interface ValidateDatasetParams extends BuildDatasetParams {
  required_columns?: string[];
  rules?: string[];
}

/** The full validation rule catalogue: name, category, description, default severity. */
export async function fetchValidationRules(): Promise<ValidationRuleCatalog> {
  const { data } = await apiClient.get('/api/v1/validation/rules');
  return ValidationRuleCatalogSchema.parse(data);
}

/** Build a dataset for one market/timeframe/range and validate it. */
export async function validateDataset(
  symbol: string,
  params: ValidateDatasetParams,
): Promise<ValidationReport> {
  const { data } = await apiClient.post(
    `/api/v1/markets/${encodeURIComponent(symbol)}/features/validate`,
    params,
  );
  return ValidationReportSchema.parse(data);
}
