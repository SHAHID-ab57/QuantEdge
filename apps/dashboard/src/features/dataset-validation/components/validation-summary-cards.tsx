'use client';

import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import GridViewIcon from '@mui/icons-material/GridView';
import InfoIcon from '@mui/icons-material/Info';
import RuleIcon from '@mui/icons-material/Rule';
import SpeedIcon from '@mui/icons-material/Speed';
import TableRowsIcon from '@mui/icons-material/TableRows';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import ViewWeekIcon from '@mui/icons-material/ViewWeek';
import WarningIcon from '@mui/icons-material/Warning';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { computeQualityScore, qualityBand } from '../lib/quality-score';

export interface ValidationSummaryCardsProps {
  report: ValidationReport;
  /**
   * How many features were requested to build this dataset. Sourced from
   * the page's own selection state, not the report itself — the report
   * carries `rows`/`columns` but not a feature count, since validating a
   * dataset doesn't require knowing how it was assembled.
   */
  featureCount: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  structural: 'Structural',
  data_quality: 'Data Quality',
  time_series: 'Time-Series',
  feature: 'Feature',
};

function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

const QUALITY_BAND_COLOR = {
  excellent: 'success.main',
  good: 'success.main',
  fair: 'warning.main',
  poor: 'error.main',
} as const;

interface CardProps {
  label: string;
  value: string;
  icon: ReactNode;
  color: string;
  help?: string;
}

function Card({ label, value, icon, color, help }: CardProps) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, minWidth: 150, flex: '1 1 150px', borderColor: 'divider' }}
    >
      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ color }}>
        {icon}
        <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
          {label}
        </Typography>
        {help ? <InfoTooltip label={label} sections={[{ heading: label, body: help }]} /> : null}
      </Stack>
      <Typography
        variant="h5"
        sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', mt: 0.5 }}
      >
        {value}
      </Typography>
    </Paper>
  );
}

/**
 * The quality gate's verdict, at a glance: pass/fail, then how many
 * errors, warnings, and info-level findings — followed by dataset-shape
 * metrics (size, rows, columns, features, rules executed, validation
 * time), a derived Quality Score, and one card per validation category
 * (structural, data quality, time-series, feature) so a researcher can
 * immediately tell *which kind* of problem a dataset has, without reading
 * the full issue list first.
 */
export function ValidationSummaryCards({ report, featureCount }: ValidationSummaryCardsProps) {
  const { summary, categories } = report;
  const qualityScore = computeQualityScore(summary);
  const band = qualityBand(qualityScore);

  return (
    <Stack spacing={1.5} aria-label="Validation summary">
      <Stack direction="row" flexWrap="wrap" useFlexGap gap={1.5}>
        <Card
          label="Result"
          value={report.passed ? 'Passed' : 'Failed'}
          icon={
            report.passed ? <CheckCircleIcon fontSize="small" /> : <ErrorIcon fontSize="small" />
          }
          color={report.passed ? 'success.main' : 'error.main'}
          help="False only when at least one error-severity issue was found. Warnings and info findings are always reported but never fail this gate."
        />
        <Card
          label="Quality Score"
          value={`${qualityScore}`}
          icon={<SpeedIcon fontSize="small" />}
          color={QUALITY_BAND_COLOR[band]}
          help="A simple heuristic for scanning many datasets quickly — not a scientific metric. Starts at 100 and subtracts 15 per error and 5 per warning, floored at 0."
        />
        <Card
          label="Errors"
          value={summary.errors.toLocaleString()}
          icon={<ErrorIcon fontSize="small" />}
          color="error.main"
          help="Findings that fail the quality gate — this dataset should not be used for training or backtesting until these are resolved."
        />
        <Card
          label="Warnings"
          value={summary.warnings.toLocaleString()}
          icon={<WarningIcon fontSize="small" />}
          color="warning.main"
          help="Findings worth investigating, but that do not block the dataset from being used."
        />
        <Card
          label="Info"
          value={summary.info.toLocaleString()}
          icon={<InfoIcon fontSize="small" />}
          color="info.main"
          help="Informational findings, for context only."
        />
      </Stack>

      <Stack direction="row" flexWrap="wrap" useFlexGap gap={1.5}>
        <Card
          label="Dataset Size"
          value={(report.rows * report.columns).toLocaleString()}
          icon={<GridViewIcon fontSize="small" />}
          color="text.secondary"
          help="Total cells in the dataset — rows multiplied by columns."
        />
        <Card
          label="Rows"
          value={report.rows.toLocaleString()}
          icon={<TableRowsIcon fontSize="small" />}
          color="text.secondary"
        />
        <Card
          label="Columns"
          value={report.columns.toLocaleString()}
          icon={<ViewColumnIcon fontSize="small" />}
          color="text.secondary"
        />
        <Card
          label="Features"
          value={featureCount.toLocaleString()}
          icon={<ViewWeekIcon fontSize="small" />}
          color="text.secondary"
          help="How many feature generators were requested to build this dataset."
        />
        <Card
          label="Rules Executed"
          value={report.rules_run.length.toLocaleString()}
          icon={<RuleIcon fontSize="small" />}
          color="text.secondary"
          help="How many validation rules ran against this dataset — every registered rule by default, or a caller-chosen subset."
        />
        <Card
          label="Validation Time"
          value={`${report.duration_ms.toFixed(1)} ms`}
          icon={<SpeedIcon fontSize="small" />}
          color="text.secondary"
          help="Wall-clock time spent running every validation rule."
        />
      </Stack>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 1,
        }}
      >
        {Object.entries(categories).map(([category, counts]) => (
          <Paper
            key={category}
            variant="outlined"
            sx={{ p: 1, borderColor: 'divider', textAlign: 'center' }}
          >
            <Typography variant="caption" color="text.secondary" component="p">
              {categoryLabel(category)}
            </Typography>
            <Typography
              variant="body2"
              sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
            >
              {counts.errors + counts.warnings + counts.info === 0
                ? 'Clean'
                : `${counts.errors}E · ${counts.warnings}W · ${counts.info}I`}
            </Typography>
          </Paper>
        ))}
      </Box>
    </Stack>
  );
}
