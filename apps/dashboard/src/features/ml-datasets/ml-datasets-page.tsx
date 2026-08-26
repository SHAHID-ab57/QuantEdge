'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useCallback, useMemo, useState } from 'react';
import { Section } from '@/components/section';
import { ValidationReportPanel } from '@/features/dataset-validation/components/validation-report-panel';
import { ValidationSummaryCards } from '@/features/dataset-validation/components/validation-summary-cards';
import {
  DatasetForm,
  type DatasetFormValues,
} from '@/features/feature-engineering/components/dataset-form';
import { DatasetPreviewTable } from '@/features/feature-engineering/components/dataset-preview-table';
import { FeatureSelector } from '@/features/feature-engineering/components/feature-selector';
import { useFeatureCatalog } from '@/features/feature-engineering/hooks/use-feature-data';
import {
  toRequestBodies,
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from '@/features/feature-engineering/lib/feature-selection';
import { useMarkets } from '@/features/history/hooks/use-history-data';
import type { BuildMLDatasetParams } from '@/lib/api/ml-datasets';
import { toDatasetRange } from '@/lib/resolve-dataset-range';
import type { Feature } from '@/types/api/features';
import type { TargetDTO } from '@/types/api/ml-datasets';
import { DatasetConfigActions } from './components/dataset-config-actions';
import { MLDatasetExport } from './components/ml-dataset-export';
import { MLDatasetInfoCard } from './components/ml-dataset-info-card';
import { MLDatasetMetadataPanel } from './components/ml-dataset-metadata-panel';
import { MLDatasetSummary } from './components/ml-dataset-summary';
import { SplitConfigForm } from './components/split-config-form';
import { TargetSelector } from './components/target-selector';
import { PREVIEW_ROWS, useBuildMLDataset, useTargetCatalog } from './hooks/use-ml-dataset-data';
import { dataRangeText } from './lib/data-range-text';
import { serializeDatasetConfig, type DatasetConfig } from './lib/dataset-config';
import { validateSplitRatios, type SplitRatioValues } from './lib/split-ratios';
import { targetProblemTypeLabel } from './lib/target-type';
import {
  toTargetRequestBodies,
  toggleTargetSelection,
  updateTargetSelectionParams,
  type TargetSelection,
} from './lib/target-selection';

const INITIAL_FORM: DatasetFormValues = {
  market: '',
  timeframe: '',
  range: 'all',
  start: '',
  end: '',
  limit: 500,
};

const INITIAL_SPLIT: SplitRatioValues = { train: 0.7, validation: 0.15, test: 0.15 };

function buildParams(
  values: DatasetFormValues,
  featureSelections: readonly FeatureSelection[],
  targetSelections: readonly TargetSelection[],
  split: SplitRatioValues,
): BuildMLDatasetParams {
  return {
    timeframe: values.timeframe,
    ...toDatasetRange(values),
    limit: values.limit,
    features: toRequestBodies(featureSelections),
    targets: toTargetRequestBodies(targetSelections),
    split_train: split.train,
    split_validation: split.validation,
    split_test: split.test,
    preview_rows: PREVIEW_ROWS,
  };
}

function PageSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading ML dataset builder">
      <Skeleton variant="rounded" height={72} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Skeleton variant="rounded" height={320} />
        </Grid>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Skeleton variant="rounded" height={320} />
        </Grid>
      </Grid>
    </Stack>
  );
}

/**
 * The ML Dataset Builder workbench: pick a market, timeframe, and range,
 * choose features (model inputs) and prediction targets (labels), set a
 * chronological train/validation/test split, build the dataset, inspect
 * its versioning and validation verdict, and export it.
 *
 * This is the only supported path for producing a dataset used in AI
 * training — see `ARCHITECTURE.md` § "ML Dataset Builder". It deliberately
 * reuses the Feature Engineering page's own `DatasetForm` and
 * `FeatureSelector` (the same market/timeframe/range/feature selection
 * that builds a plain feature dataset also builds an ML dataset, plus
 * targets and a split) and the Dataset Validation page's
 * `ValidationSummaryCards`/`ValidationReportPanel` (the embedded
 * validation verdict is the exact same `ValidationReport` shape either
 * page renders) — matching this session's established precedent of never
 * declaring a second dataset-selection or validation-rendering UI.
 *
 * Building is an explicit action, not a reactive one, for the same reason
 * `FeatureEngineeringPage` treats it that way: a potentially expensive
 * server-side computation must never fire as a side effect of ticking a
 * checkbox.
 */
export function MLDatasetsPage() {
  const markets = useMarkets();
  const featureCatalogue = useFeatureCatalog();
  const targetCatalogue = useTargetCatalog();
  const build = useBuildMLDataset();

  const [form, setForm] = useState<DatasetFormValues>(INITIAL_FORM);
  const [featureSelections, setFeatureSelections] = useState<FeatureSelection[]>([]);
  const [targetSelections, setTargetSelections] = useState<TargetSelection[]>([]);
  const [split, setSplit] = useState<SplitRatioValues>(INITIAL_SPLIT);
  /** The request that produced the dataset on screen — so exports match it exactly. */
  const [built, setBuilt] = useState<{ symbol: string; params: BuildMLDatasetParams } | null>(null);

  const features = useMemo(() => featureCatalogue.data?.features ?? [], [featureCatalogue.data]);
  const targets = useMemo(() => targetCatalogue.data?.targets ?? [], [targetCatalogue.data]);

  const handleFeatureToggle = useCallback((feature: Feature) => {
    setFeatureSelections((current) => toggleSelection(current, feature));
  }, []);

  const handleFeatureParamsChange = useCallback(
    (feature: string, params: Record<string, string>) => {
      setFeatureSelections((current) => updateSelectionParams(current, feature, params));
    },
    [],
  );

  const handleTargetToggle = useCallback((target: TargetDTO) => {
    setTargetSelections((current) => toggleTargetSelection(current, target));
  }, []);

  const handleTargetParamsChange = useCallback((target: string, params: Record<string, string>) => {
    setTargetSelections((current) => updateTargetSelectionParams(current, target, params));
  }, []);

  const splitError = validateSplitRatios(split);
  const noFeatures = featureSelections.length === 0;
  const noTargets = targetSelections.length === 0;
  const canSubmit = !noFeatures && !noTargets && splitError === null;

  const handleSubmit = useCallback(() => {
    if (!canSubmit) {
      return;
    }
    const params = buildParams(form, featureSelections, targetSelections, split);
    setBuilt({ symbol: form.market, params });
    build.mutate({ symbol: form.market, params });
  }, [build, canSubmit, form, featureSelections, targetSelections, split]);

  const currentConfig = useMemo(
    () => serializeDatasetConfig(form, featureSelections, targetSelections, split),
    [form, featureSelections, targetSelections, split],
  );

  const handleImportConfig = useCallback((config: DatasetConfig) => {
    setForm({
      market: config.market,
      timeframe: config.timeframe,
      range: config.range,
      start: config.start,
      end: config.end,
      limit: config.limit,
    });
    setFeatureSelections(
      config.features.map((entry) => ({ feature: entry.feature, params: entry.params })),
    );
    setTargetSelections(
      config.targets.map((entry) => ({ target: entry.target, params: entry.params })),
    );
    setSplit(config.split);
  }, []);

  const targetProblemTypes = useMemo(
    () =>
      Object.fromEntries(targets.map((target) => [target.name, targetProblemTypeLabel(target)])),
    [targets],
  );

  if (markets.isLoading || featureCatalogue.isLoading || targetCatalogue.isLoading) {
    return <PageSkeleton />;
  }

  if (markets.isError || featureCatalogue.isError || targetCatalogue.isError) {
    const message =
      markets.error?.message ??
      featureCatalogue.error?.message ??
      targetCatalogue.error?.message ??
      'Unknown error';
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button
            onClick={() => {
              markets.refetch();
              featureCatalogue.refetch();
              targetCatalogue.refetch();
            }}
          >
            Retry
          </Button>
        }
      >
        Failed to load the ML dataset builder: {message}
      </Alert>
    );
  }

  const dataset = build.data;

  return (
    <Stack spacing={2}>
      <Section
        title="Dataset Configuration"
        subtitle="Market, timeframe, date range, and chronological split for the ML dataset"
      >
        <Stack spacing={1.5}>
          <DatasetForm
            markets={markets.data?.markets}
            values={form}
            onChange={setForm}
            onSubmit={handleSubmit}
            busy={build.isPending}
            canSubmit={canSubmit}
            submitLabel="Build ML Dataset"
            busyLabel="Building…"
          />
          {noFeatures ? (
            <Typography variant="caption" color="text.secondary">
              Select at least one feature to build a dataset.
            </Typography>
          ) : null}
          {noTargets ? (
            <Typography variant="caption" color="text.secondary">
              Select at least one prediction target to build a dataset.
            </Typography>
          ) : null}
          <Typography variant="subtitle2">Split Configuration</Typography>
          <SplitConfigForm
            values={split}
            onChange={setSplit}
            estimatedTotalRows={dataset?.meta.total_rows}
          />
          <Typography variant="subtitle2">Reproducibility</Typography>
          <DatasetConfigActions config={currentConfig} onImport={handleImportConfig} />
        </Stack>
      </Section>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack spacing={2}>
            <Section
              title="Features"
              subtitle={`${featureSelections.length} of ${features.length} selected`}
            >
              <FeatureSelector
                features={features}
                loading={featureCatalogue.isLoading}
                selections={featureSelections}
                onToggle={handleFeatureToggle}
                onParamsChange={handleFeatureParamsChange}
              />
            </Section>

            <Section
              title="Prediction Targets"
              subtitle={`${targetSelections.length} of ${targets.length} selected`}
            >
              <TargetSelector
                targets={targets}
                loading={targetCatalogue.isLoading}
                selections={targetSelections}
                onToggle={handleTargetToggle}
                onParamsChange={handleTargetParamsChange}
              />
            </Section>

            {dataset ? (
              <Section title="ML Dataset Information" subtitle="Identity and versioning chain">
                <MLDatasetInfoCard dataset={dataset} />
              </Section>
            ) : null}

            {dataset ? (
              <Section title="Dataset Summary" subtitle="How trustworthy this dataset is">
                <MLDatasetSummary
                  dataset={dataset}
                  dataRangeText={dataRangeText(form)}
                  targetProblemTypes={targetProblemTypes}
                />
              </Section>
            ) : null}

            {dataset ? (
              <Section
                title="Dataset Metadata"
                subtitle="What produced this file, and where it came from"
              >
                <MLDatasetMetadataPanel dataset={dataset} dataRangeText={dataRangeText(form)} />
              </Section>
            ) : null}

            {dataset && built ? (
              <Section title="Export" subtitle="Download the complete, split dataset">
                <MLDatasetExport
                  symbol={built.symbol}
                  timeframe={dataset.timeframe}
                  params={built.params}
                  dataset={dataset}
                />
              </Section>
            ) : null}
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, lg: 8 }}>
          <Stack spacing={2}>
            {build.isPending ? (
              <Stack spacing={1} role="status" aria-label="Building ML dataset">
                <Skeleton variant="rounded" height={40} />
                <Skeleton variant="rounded" height={200} />
              </Stack>
            ) : null}

            {!build.isPending && build.isError ? (
              <Alert
                severity="error"
                role="alert"
                action={
                  <Button onClick={handleSubmit} disabled={!canSubmit}>
                    Retry
                  </Button>
                }
              >
                {build.error instanceof Error
                  ? build.error.message
                  : 'The ML dataset could not be built.'}
              </Alert>
            ) : null}

            {!build.isPending && !build.isError && dataset ? (
              <>
                <Section
                  title="Validation Summary"
                  subtitle={`${dataset.symbol} · ${dataset.timeframe}`}
                >
                  <ValidationSummaryCards
                    report={dataset.validation}
                    featureCount={dataset.feature_columns.length}
                  />
                </Section>

                <Section
                  title="Dataset Preview"
                  subtitle="One row per candle, feature and target columns, plus each row's split"
                >
                  <DatasetPreviewTable
                    dataset={dataset}
                    targetColumns={dataset.target_columns}
                    splitLabels={dataset.split}
                  />
                </Section>

                <Section
                  title="Validation Report"
                  subtitle="Every finding from the leakage/quality run"
                >
                  <ValidationReportPanel report={dataset.validation} />
                </Section>
              </>
            ) : null}

            {!build.isPending && !build.isError && !dataset ? (
              <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  Choose a market, timeframe, features, and prediction targets, then build a dataset
                  to preview it here.
                </Typography>
              </Paper>
            ) : null}
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  );
}
