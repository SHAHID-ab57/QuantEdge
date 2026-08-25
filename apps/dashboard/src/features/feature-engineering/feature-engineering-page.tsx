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
import { resolveRange } from '@/features/history/lib/resolve-range';
import type { BuildDatasetParams } from '@/lib/api/features';
import type { Feature } from '@/types/api/features';
import { DatasetExport } from './components/dataset-export';
import { DatasetForm, type DatasetFormValues } from './components/dataset-form';
import { DatasetInfoCard } from './components/dataset-info-card';
import { DatasetPreviewTable } from './components/dataset-preview-table';
import { DatasetSummary } from './components/dataset-summary';
import { FeatureSelector } from './components/feature-selector';
import { PREVIEW_ROWS, useBuildDataset, useFeatureCatalog } from './hooks/use-feature-data';
import {
  toRequestBodies,
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from './lib/feature-selection';

const DAY_MS = 86_400_000;

const INITIAL_FORM: DatasetFormValues = {
  market: '',
  timeframe: '',
  range: 'all',
  start: '',
  end: '',
  limit: 500,
};

/**
 * Convert the form's date inputs into the half-open UTC bounds the API
 * expects, matching the History page's own conversion exactly — the end day
 * is included in full, so "1st to 2nd" covers both days entirely.
 */
function toRange(values: DatasetFormValues): { start?: string; end?: string } {
  if (values.range === 'custom') {
    if (!values.start || !values.end) {
      return {};
    }
    const end = new Date(new Date(`${values.end}T00:00:00Z`).getTime() + DAY_MS)
      .toISOString()
      .replace(/\.\d{3}Z$/, 'Z');
    return { start: `${values.start}T00:00:00Z`, end };
  }
  const resolved = resolveRange(values.range);
  return { start: resolved.start ?? undefined, end: resolved.end ?? undefined };
}

function buildParams(
  values: DatasetFormValues,
  selections: readonly FeatureSelection[],
): BuildDatasetParams {
  return {
    timeframe: values.timeframe,
    ...toRange(values),
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
