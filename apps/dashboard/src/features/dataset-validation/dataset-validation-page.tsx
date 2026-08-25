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
import {
  DatasetForm,
  type DatasetFormValues,
} from '@/features/feature-engineering/components/dataset-form';
import { FeatureSelector } from '@/features/feature-engineering/components/feature-selector';
import { useFeatureCatalog } from '@/features/feature-engineering/hooks/use-feature-data';
import {
  defaultParamsFor,
  toRequestBodies,
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from '@/features/feature-engineering/lib/feature-selection';
import { useMarkets } from '@/features/history/hooks/use-history-data';
import type { ValidateDatasetParams } from '@/lib/api/dataset-validation';
import { toDatasetRange } from '@/lib/resolve-dataset-range';
import type { Feature } from '@/types/api/features';
import { RequiredColumnPresets } from './components/required-column-presets';
import { RequiredColumnsSelector } from './components/required-columns-selector';
import { ValidationReportDownload } from './components/validation-report-download';
import { ValidationReportPanel } from './components/validation-report-panel';
import { ValidationRuleCatalog } from './components/validation-rule-catalog';
import { ValidationStatistics } from './components/validation-statistics';
import { ValidationSummaryCards } from './components/validation-summary-cards';
import { useRunValidation, useValidationRuleCatalog } from './hooks/use-dataset-validation';
import {
  resolveRequiredColumnOptions,
  resolvePresetFeatures,
  type ColumnPresetKey,
} from './lib/resolve-required-columns';

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
  requiredColumns: readonly string[],
): ValidateDatasetParams {
  return {
    timeframe: values.timeframe,
    ...toDatasetRange(values),
    limit: values.limit,
    features: toRequestBodies(selections),
    required_columns: [...requiredColumns],
  };
}

function PageSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading dataset validation">
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

/** What this page does, how to start, and a worked example — shown before anything has been validated yet. */
function GettingStarted() {
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="subtitle2">What validation does</Typography>
        <Typography variant="body2" color="text.secondary">
          Builds a dataset — the same one the Feature Engineering page builds — and runs the
          validation engine&apos;s full rule suite over it: structural checks (do the promised
          columns exist, do types match), data-quality checks (missing values, duplicates, NaN,
          infinities), time-series checks (ordering, gaps), and feature checks (did every requested
          feature actually generate). The result is a pass/fail verdict plus a structured report
          explaining exactly what, if anything, is wrong.
        </Typography>

        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          How to start
        </Typography>
        <Typography variant="body2" color="text.secondary" component="div">
          1. Pick a Market and Timeframe above.
          <br />
          2. Choose one or more Features on the left — or apply a Preset for a quick start.
          <br />
          3. Optionally require specific columns beyond what the features already imply.
          <br />
          4. Press Run Validation.
        </Typography>

        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          Example workflow
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Apply the &quot;AI Basic Features&quot; preset, pick ETHUSD at 1h over Last 30 Days, and
          run validation. A clean result means that exact dataset is safe to export and train on;
          any reported errors name precisely which check failed and why.
        </Typography>
      </Stack>
    </Paper>
  );
}

/**
 * The Dataset Validation & Quality workbench: pick a market, timeframe,
 * range, and features — the same selection a dataset build uses — then
 * run the validation engine's full rule suite over the resulting dataset
 * and inspect the structured quality report.
 *
 * Deliberately reuses the Feature Engineering page's own `DatasetForm` and
 * `FeatureSelector` rather than declaring a second dataset-selection UI:
 * `/features/validate`'s request body is a `FeatureDatasetRequest` plus
 * two validation-only fields, so the exact same selection controls that
 * build a dataset also validate one — see `ARCHITECTURE.md` § "Dataset
 * Validation & Quality Engine" for why building is never duplicated here.
 */
export function DatasetValidationPage() {
  const markets = useMarkets();
  const catalogue = useFeatureCatalog();
  const ruleCatalogue = useValidationRuleCatalog();
  const validation = useRunValidation();

  const [form, setForm] = useState<DatasetFormValues>(INITIAL_FORM);
  const [selections, setSelections] = useState<FeatureSelection[]>([]);
  const [requiredColumns, setRequiredColumns] = useState<string[]>([]);

  const features = useMemo(() => catalogue.data?.features ?? [], [catalogue.data]);

  const handleToggle = useCallback((feature: Feature) => {
    setSelections((current) => toggleSelection(current, feature));
  }, []);

  const handleParamsChange = useCallback((feature: string, params: Record<string, string>) => {
    setSelections((current) => updateSelectionParams(current, feature, params));
  }, []);

  const handleApplyPreset = useCallback(
    (key: ColumnPresetKey) => {
      const presetFeatures = resolvePresetFeatures(features, key);
      const nextSelections = presetFeatures.map((feature) => ({
        feature: feature.name,
        params: defaultParamsFor(feature),
      }));
      setSelections(nextSelections);
      setRequiredColumns(
        resolveRequiredColumnOptions(presetFeatures, nextSelections).map((option) => option.name),
      );
    },
    [features],
  );

  const handleSubmit = useCallback(() => {
    const params = buildParams(form, selections, requiredColumns);
    validation.mutate({ symbol: form.market, params });
  }, [form, selections, requiredColumns, validation]);

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
        Failed to load the validation workbench: {message}
      </Alert>
    );
  }

  const report = validation.data;
  const noFeatures = selections.length === 0;

  return (
    <Stack spacing={2}>
      <Section
        title="Dataset Configuration"
        subtitle="Market, timeframe, and date range to validate — the same selection a dataset build uses"
      >
        <Stack spacing={1.5}>
          <DatasetForm
            markets={markets.data?.markets}
            values={form}
            onChange={setForm}
            onSubmit={handleSubmit}
            busy={validation.isPending}
            canSubmit={!noFeatures}
            submitLabel="Run Validation"
            busyLabel="Validating…"
          />
          {noFeatures ? (
            <Typography variant="caption" color="text.secondary">
              Select at least one feature to validate a dataset.
            </Typography>
          ) : null}

          <RequiredColumnPresets onApply={handleApplyPreset} disabled={features.length === 0} />

          <RequiredColumnsSelector
            features={features}
            selections={selections}
            value={requiredColumns}
            onChange={setRequiredColumns}
          />
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

            <Section title="Available Checks" subtitle="Every rule the engine runs by default">
              <ValidationRuleCatalog
                catalogue={ruleCatalogue.data}
                loading={ruleCatalogue.isLoading}
              />
            </Section>
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, lg: 8 }}>
          <Stack spacing={2}>
            {validation.isPending ? (
              <Stack spacing={1} role="status" aria-label="Running validation">
                <Skeleton variant="rounded" height={40} />
                <Skeleton variant="rounded" height={200} />
              </Stack>
            ) : null}

            {!validation.isPending && validation.isError ? (
              <Alert
                severity="error"
                role="alert"
                action={
                  <Button onClick={handleSubmit} disabled={noFeatures}>
                    Retry
                  </Button>
                }
              >
                {validation.error instanceof Error
                  ? validation.error.message
                  : 'Validation could not be completed.'}
              </Alert>
            ) : null}

            {!validation.isPending && !validation.isError && report ? (
              <>
                <Section
                  title="Validation Summary"
                  subtitle={`${report.symbol} · ${report.timeframe}`}
                  action={<ValidationReportDownload report={report} />}
                >
                  <ValidationSummaryCards report={report} featureCount={selections.length} />
                </Section>

                <Section title="Validation Report" subtitle="Every finding from this run">
                  <ValidationReportPanel report={report} />
                </Section>

                <Section title="Statistics" subtitle="What was validated, and how">
                  <ValidationStatistics report={report} />
                </Section>
              </>
            ) : null}

            {!validation.isPending && !validation.isError && !report ? <GettingStarted /> : null}
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  );
}
