import type {
  FeatureRequest,
  SplitConfig,
  TargetRequest,
  Experiment,
} from '@/types/api/experiments';
import type { DatasetFeatureInfo } from '@/types/api/features';
import type { DatasetTargetInfo, MLDatasetResponse } from '@/types/api/ml-datasets';
import type { FeatureSelection } from '@/features/feature-engineering/lib/feature-selection';
import type { SplitRatioValues } from '@/features/ml-datasets/lib/split-ratios';
import type { TargetSelection } from '@/features/ml-datasets/lib/target-selection';

/**
 * Pure mapping helpers between an `Experiment`'s reproducibility record
 * (`feature_set`/`target_config`/`split_config`) and the selection state
 * `FeatureSelector`/`TargetSelector`/`SplitConfigForm` already use on
 * `/ml-datasets` — the exact same shapes, never a parallel one, so
 * `ExperimentConfigDialog` is just those three components pre-populated
 * from whatever the experiment currently records (empty state: nothing
 * selected). Kept free of React so the round-trip is testable without
 * mounting anything, matching `feature-selection.ts`/`target-selection.ts`'s
 * own convention.
 */

/** The same default ratios the ML Dataset Builder's own form seeds. */
export const DEFAULT_EXPERIMENT_SPLIT: SplitRatioValues = {
  train: 0.7,
  validation: 0.15,
  test: 0.15,
};

export function experimentToFeatureSelections(experiment: Experiment): FeatureSelection[] {
  return (experiment.feature_set ?? []).map((entry) => ({
    feature: entry.feature,
    params: entry.params,
  }));
}

export function experimentToTargetSelections(experiment: Experiment): TargetSelection[] {
  return (experiment.target_config ?? []).map((entry) => ({
    target: entry.target,
    params: entry.params,
  }));
}

export function experimentToSplitValues(experiment: Experiment): SplitRatioValues {
  return experiment.split_config ?? { ...DEFAULT_EXPERIMENT_SPLIT };
}

export interface ExperimentConfigPatch {
  feature_set: FeatureRequest[];
  target_config: TargetRequest[];
  split_config: SplitConfig;
}

/**
 * The exact `PATCH /experiments/{id}` body shape for saving the editor's
 * state — field-for-field identical to what `toRequestBodies`/
 * `toTargetRequestBodies` (the ML Dataset Builder's own request-body
 * mappers) produce, so this never invents a second shape for the same
 * `{feature, params}`/`{target, params}` data.
 */
export function buildExperimentConfigPatch(
  featureSelections: readonly FeatureSelection[],
  targetSelections: readonly TargetSelection[],
  split: SplitRatioValues,
): ExperimentConfigPatch {
  return {
    feature_set: featureSelections.map((selection) => ({
      feature: selection.feature,
      params: selection.params,
    })),
    target_config: targetSelections.map((selection) => ({
      target: selection.target,
      params: selection.params,
    })),
    split_config: split,
  };
}

/**
 * Fully-resolved parameter values (numbers, booleans, …) as the strings
 * `FeatureSelector`/`TargetSelector`'s parameter inputs expect — a dataset
 * build's `DatasetFeatureInfo`/`DatasetTargetInfo.parameters` records what
 * actually ran, typed, while a selection's own `params` is always a
 * `Record<string, string>` edited through a text input.
 */
function stringifyParams(params: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)]));
}

export interface ImportedDatasetConfig {
  features: FeatureSelection[];
  targets: TargetSelection[];
  split: SplitRatioValues;
}

/**
 * Map one past dataset build's stored payload onto the editor's own
 * selection state — the whole of the "Import from Dataset History" action.
 * Given the `MLDatasetResponse` a `GET /ml/dataset-builds/{id}` returns,
 * this removes hand-copying JSON between the ML Dataset Builder and an
 * Experiment entirely.
 */
export function datasetBuildToConfig(dataset: MLDatasetResponse): ImportedDatasetConfig {
  return {
    features: dataset.features.map((entry: DatasetFeatureInfo) => ({
      feature: entry.feature,
      params: stringifyParams(entry.parameters),
    })),
    targets: dataset.targets.map((entry: DatasetTargetInfo) => ({
      target: entry.target,
      params: stringifyParams(entry.parameters),
    })),
    split: { ...dataset.split_ratios },
  };
}
