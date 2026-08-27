'use client';

import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMemo } from 'react';
import { Section } from '@/components/section';
import { ValidationReportPanel } from '@/features/dataset-validation/components/validation-report-panel';
import { ValidationSummaryCards } from '@/features/dataset-validation/components/validation-summary-cards';
import { DatasetPreviewTable } from '@/features/feature-engineering/components/dataset-preview-table';
import { useMLDatasetBuild, useTargetCatalog } from '../hooks/use-ml-dataset-data';
import { historicalRangeText } from '../lib/data-range-text';
import { targetProblemTypeLabel } from '../lib/target-type';
import { MLDatasetInfoCard } from './ml-dataset-info-card';
import { MLDatasetMetadataPanel } from './ml-dataset-metadata-panel';
import { MLDatasetSummary } from './ml-dataset-summary';

export interface DatasetHistoryDetailDialogProps {
  buildId: string | null;
  onClose: () => void;
}

/**
 * Reopens one past ML dataset build exactly as it looked when it was
 * built — the same Info/Summary/Metadata/Preview/Validation panels the
 * builder page itself renders for a fresh build, given the persisted
 * `MLDatasetResponse` instead of a freshly-built one. No re-fetch of
 * candles happens here; every value on screen came from `payload` in
 * `ml_dataset_builds`, verbatim.
 */
export function DatasetHistoryDetailDialog({ buildId, onClose }: DatasetHistoryDetailDialogProps) {
  const build = useMLDatasetBuild(buildId);
  const targetCatalogue = useTargetCatalog();

  const targets = useMemo(() => targetCatalogue.data?.targets ?? [], [targetCatalogue.data]);
  const targetProblemTypes = useMemo(
    () =>
      Object.fromEntries(targets.map((target) => [target.name, targetProblemTypeLabel(target)])),
    [targets],
  );

  const data = build.data;
  const dataset = data?.dataset;

  return (
    <Dialog open={Boolean(buildId)} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        {dataset ? `${dataset.symbol} · ${dataset.timeframe}` : 'ML Dataset Build'}
      </DialogTitle>
      <DialogContent>
        {build.isLoading ? (
          <Stack alignItems="center" sx={{ py: 4 }}>
            <CircularProgress size={24} aria-label="Loading dataset build" />
          </Stack>
        ) : null}

        {build.isError ? (
          <Alert severity="error" role="alert">
            {build.error instanceof Error
              ? build.error.message
              : 'Failed to load this dataset build.'}
          </Alert>
        ) : null}

        {dataset && data ? (
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Built {new Date(data.created_at).toLocaleString()} ·{' '}
              {historicalRangeText(dataset.timestamps)}
            </Typography>

            <Section title="ML Dataset Information" subtitle="Identity and versioning chain">
              <MLDatasetInfoCard dataset={dataset} />
            </Section>

            <Section title="Dataset Summary" subtitle="How trustworthy this dataset is">
              <MLDatasetSummary
                dataset={dataset}
                dataRangeText={historicalRangeText(dataset.timestamps)}
                targetProblemTypes={targetProblemTypes}
              />
            </Section>

            <Section
              title="Dataset Metadata"
              subtitle="What produced this file, and where it came from"
            >
              <MLDatasetMetadataPanel
                dataset={dataset}
                dataRangeText={historicalRangeText(dataset.timestamps)}
              />
            </Section>

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
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
