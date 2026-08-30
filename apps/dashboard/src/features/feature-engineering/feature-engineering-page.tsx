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
import { useMarkets } from '@/features/history/hooks/use-history-data';
import type { BuildDatasetParams } from '@/lib/api/features';
import { toDatasetRange } from '@/lib/resolve-dataset-range';
import type { Feature } from '@/types/api/features';
import { DatasetExport } from './components/dataset-export';
import { DatasetForm, type DatasetFormValues } from './components/dataset-form';
import { DatasetInfoCard } from './components/dataset-info-card';
import { DatasetPreviewTable } from './components/dataset-preview-table';
import { DatasetSummary } from './components/dataset-summary';
import { FeatureAnalysisPanel } from './components/feature-analysis-panel';
import { FeatureLineagePanel } from './components/feature-lineage-panel';
import { FeatureSelector } from './components/feature-selector';
import {
  PREVIEW_ROWS,
  useBuildDataset,
  useFeatureCatalog,
  useFeatureLineage,
} from './hooks/use-feature-data';
import {
  toRequestBodies,
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from './lib/feature-selection';

const INITIAL_FORM: DatasetFormValues = {
  market: '',
  timeframe: '',
  range: 'all',
  start: '',
  end: '',
  limit: 500,
};

function buildParams(
  values: DatasetFormValues,
  selections: readonly FeatureSelection[],
): BuildDatasetParams {
  return {
    timeframe: values.timeframe,
    ...toDatasetRange(values),
    limit: values.limit,
    features: toRequestBodies(selections),
    preview_rows: PREVIEW_ROWS,
  };
}

function PageSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading feature engineering">
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
 * The Feature Engineering workbench: pick a market, timeframe and range,
 * choose features, build the dataset, inspect it, and export it.
 *
 * Everything on this page is driven by the backend's feature catalogue —
 * the selector, every parameter input, and every column header come from
 * the API response rather than from anything hardcoded here. Registering a
 * new generator on the backend therefore adds it to this page with no
 * frontend change, which is the whole point of the registry.
 *
 * The dataset is built on an explicit "Build Dataset" action rather than
 * reactively as the form changes: it is a deliberate, potentially
 * expensive computation, and firing it on every checkbox tick would make
 * the page unusable for exactly the researchers it is meant to serve.
 */
export function FeatureEngineeringPage() {
  const markets = useMarkets();
  const catalogue = useFeatureCatalog();
  const build = useBuildDataset();
  const lineage = useFeatureLineage();

  const [form, setForm] = useState<DatasetFormValues>(INITIAL_FORM);
  const [selections, setSelections] = useState<FeatureSelection[]>([]);
  /** The request that produced the dataset on screen — so exports match it exactly. */
  const [built, setBuilt] = useState<{ symbol: string; params: BuildDatasetParams } | null>(null);

  const features = useMemo(() => catalogue.data?.features ?? [], [catalogue.data]);

  const handleToggle = useCallback((feature: Feature) => {
    setSelections((current) => toggleSelection(current, feature));
  }, []);

  const handleParamsChange = useCallback((feature: string, params: Record<string, string>) => {
    setSelections((current) => updateSelectionParams(current, feature, params));
  }, []);

  const handleSubmit = useCallback(() => {
    const params = buildParams(form, selections);
    setBuilt({ symbol: form.market, params });
    build.mutate({ symbol: form.market, params });
  }, [build, form, selections]);

  if (markets.isLoading || catalogue.isLoading) {
    return <PageSkeleton />;
  }

  if (markets.isError || catalogue.isError) {
    const message = markets.error?.message ?? catalogue.error?.message ?? 'Unknown error';
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button
            onClick={() => {
              markets.refetch();
              catalogue.refetch();
            }}
          >
            Retry
          </Button>
        }
      >
        Failed to load the feature workbench: {message}
      </Alert>
    );
  }

  const dataset = build.data;
  const noFeatures = selections.length === 0;

  return (
    <Stack spacing={2}>
      <Section
        title="Dataset Configuration"
        subtitle="Market, timeframe, and date range to generate features over"
      >
        <Stack spacing={1}>
          <DatasetForm
            markets={markets.data?.markets}
            values={form}
            onChange={setForm}
            onSubmit={handleSubmit}
            busy={build.isPending}
            canSubmit={!noFeatures}
          />
          {noFeatures ? (
            <Typography variant="caption" color="text.secondary">
              Select at least one feature to build a dataset.
            </Typography>
          ) : null}
        </Stack>
      </Section>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack spacing={2}>
            <Section
              title="Features"
              subtitle={`${selections.length} of ${features.length} selected`}
            >
              <FeatureSelector
                features={features}
                loading={catalogue.isLoading}
                selections={selections}
                onToggle={handleToggle}
                onParamsChange={handleParamsChange}
              />
            </Section>

            {dataset ? (
              <Section title="Dataset Information" subtitle="Identity and reproducibility">
                <DatasetInfoCard dataset={dataset} />
              </Section>
            ) : null}

            {dataset ? (
              <Section title="Quality Report" subtitle="How trustworthy this dataset is">
                <DatasetSummary dataset={dataset} />
              </Section>
            ) : null}

            {dataset && built ? (
              <Section title="Export" subtitle="Download the complete dataset">
                <DatasetExport
                  symbol={built.symbol}
                  timeframe={dataset.timeframe}
                  params={built.params}
                />
              </Section>
            ) : null}

            {dataset && built ? (
              <Section
                title="Analysis"
                subtitle="Full-dataset statistics and a numeric correlation matrix"
              >
                <FeatureAnalysisPanel symbol={built.symbol} params={built.params} />
              </Section>
            ) : null}

            {lineage.data ? (
              <Section
                title="Dependency Graph"
                subtitle="Every registered feature's dependencies, resolved"
              >
                <FeatureLineagePanel lineage={lineage.data} />
              </Section>
            ) : null}
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, lg: 8 }}>
          <Section
            title="Dataset Preview"
            subtitle="One row per candle, one column per feature output"
          >
            {build.isPending ? (
              <Stack spacing={1} role="status" aria-label="Building dataset">
                <Skeleton variant="rounded" height={40} />
                <Skeleton variant="rounded" height={200} />
              </Stack>
            ) : null}

            {!build.isPending && build.isError ? (
              <Alert
                severity="error"
                role="alert"
                action={
                  <Button onClick={handleSubmit} disabled={noFeatures}>
                    Retry
                  </Button>
                }
              >
                {build.error instanceof Error
                  ? build.error.message
                  : 'The dataset could not be built.'}
              </Alert>
            ) : null}

            {!build.isPending && !build.isError && dataset ? (
              <DatasetPreviewTable dataset={dataset} />
            ) : null}

            {!build.isPending && !build.isError && !dataset ? (
              <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  Choose a market, timeframe, and features, then build a dataset to preview it here.
                </Typography>
              </Paper>
            ) : null}
          </Section>
        </Grid>
      </Grid>
    </Stack>
  );
}
