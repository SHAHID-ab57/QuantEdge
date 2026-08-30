'use client';

import AnalyticsIcon from '@mui/icons-material/Analytics';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { BuildDatasetParams } from '@/lib/api/features';
import { useComputeCorrelation, useComputeStatistics } from '../hooks/use-feature-data';
import { FeatureCorrelationMatrix } from './feature-correlation-matrix';
import { FeatureStatisticsPanel } from './feature-statistics-panel';

export interface FeatureAnalysisPanelProps {
  symbol: string;
  params: BuildDatasetParams;
}

/**
 * On-demand statistics and correlation for the dataset currently on screen.
 *
 * Deliberately **not** computed automatically alongside every dataset
 * build: both endpoints rebuild the same dataset server-side (see
 * `FeatureService.build_raw`'s "one dataset-building path" contract), so
 * running them on every build would double or triple the work for a
 * researcher who never looks at this panel. A single "Analyze" action
 * requests both at once, since a researcher who wants one typically wants
 * the other too, and they are cheap once the dataset itself is already
 * available server-side.
 */
export function FeatureAnalysisPanel({ symbol, params }: FeatureAnalysisPanelProps) {
  const correlation = useComputeCorrelation();
  const statistics = useComputeStatistics();

  const busy = correlation.isPending || statistics.isPending;
  const hasResult = Boolean(correlation.data || statistics.data);

  const handleAnalyze = () => {
    correlation.mutate({ symbol, params });
    statistics.mutate({ symbol, params });
  };

  const buttonLabel = () => {
    if (busy) return 'Analyzing…';
    return hasResult ? 'Re-analyze' : 'Analyze';
  };

  return (
    <Stack spacing={1.5}>
      <Button
        variant="outlined"
        startIcon={<AnalyticsIcon />}
        onClick={handleAnalyze}
        disabled={busy}
      >
        {buttonLabel()}
      </Button>

      {correlation.isError ? (
        <Alert severity="error" role="alert">
          {correlation.error instanceof Error
            ? correlation.error.message
            : 'Could not compute the correlation matrix.'}
        </Alert>
      ) : null}
      {statistics.isError ? (
        <Alert severity="error" role="alert">
          {statistics.error instanceof Error
            ? statistics.error.message
            : 'Could not compute dataset statistics.'}
        </Alert>
      ) : null}

      {statistics.data ? (
        <Stack spacing={0.5}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            Full Dataset Statistics
          </Typography>
          <FeatureStatisticsPanel statistics={statistics.data} />
        </Stack>
      ) : null}

      {correlation.data ? (
        <Stack spacing={0.5}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            Correlation Matrix
          </Typography>
          <FeatureCorrelationMatrix correlation={correlation.data} />
        </Stack>
      ) : null}
    </Stack>
  );
}
