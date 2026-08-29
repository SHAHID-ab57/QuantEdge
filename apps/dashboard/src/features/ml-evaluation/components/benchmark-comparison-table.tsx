'use client';

import DownloadIcon from '@mui/icons-material/Download';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ScienceIcon from '@mui/icons-material/Science';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { Route } from 'next';
import Link from 'next/link';
import { env } from '@/config/env';
import type { BenchmarkBestEntry, BenchmarkCandidate } from '@/types/api/evaluation';

export interface BenchmarkComparisonTableProps {
  candidates: BenchmarkCandidate[];
  bestByMetric: BenchmarkBestEntry[];
  /** The metric currently driving the "Rank" column and row order — `null`
   * falls back to `completed_at` descending (Benchmark History's own view). */
  rankMetric: string | null;
  onOpenDetail: (candidate: BenchmarkCandidate) => void;
}

/** Every metric name across every candidate, sorted, so every row shows the same columns
 * even when one candidate's job recorded a metric another's didn't (e.g. roc_auc is only
 * present for a binary/multiclass classifier that ran with probabilities available). */
export function collectMetricNames(candidates: BenchmarkCandidate[]): string[] {
  const names = new Set<string>();
  for (const candidate of candidates) {
    for (const name of Object.keys(candidate.metrics)) names.add(name);
  }
  return Array.from(names).sort();
}

function formatValue(value: number | undefined): string {
  return value === undefined ? '—' : value.toFixed(4);
}

/**
 * One row per completed training job matched by the benchmark request. With
 * no `rankMetric` chosen, rows sort by `completed_at` descending (Benchmark
 * History's own default view — see `AI.md` § "Model Evaluation &
 * Benchmarking Engine"); choosing a metric (`MetricSelector`) ranks rows by
 * that metric's value instead, direction-aware via `best_by_metric`'s own
 * `higher_is_better`, and numbers them in a "Rank" column. The winning cell
 * per metric column (from `best_by_metric`) is always highlighted,
 * independent of the current ranking metric. Each row links directly to its
 * Experiment, its Training Job, and (when recorded) its downloadable Model
 * Artifact — every href resolves to a route or download this platform
 * already serves, nothing new.
 */
export function BenchmarkComparisonTable({
  candidates,
  bestByMetric,
  rankMetric,
  onOpenDetail,
}: BenchmarkComparisonTableProps) {
  const metricNames = collectMetricNames(candidates);
  const bestJobIdByMetric = new Map(
    bestByMetric.map((entry) => [entry.metric, entry.training_job_id]),
  );
  const higherIsBetterByMetric = new Map(
    bestByMetric.map((entry) => [entry.metric, entry.higher_is_better]),
  );

  const sorted = [...candidates].sort((a, b) => {
    if (rankMetric) {
      const aValue = a.metrics[rankMetric];
      const bValue = b.metrics[rankMetric];
      if (aValue === undefined && bValue === undefined) return 0;
      if (aValue === undefined) return 1;
      if (bValue === undefined) return -1;
      const higherIsBetter = higherIsBetterByMetric.get(rankMetric) ?? true;
      return higherIsBetter ? bValue - aValue : aValue - bValue;
    }
    return (b.completed_at ?? '').localeCompare(a.completed_at ?? '');
  });

  return (
    <TableContainer>
      <Table size="small" aria-label="Model comparison">
        <TableHead>
          <TableRow>
            {rankMetric ? <TableCell align="right">Rank</TableCell> : null}
            <TableCell>Model</TableCell>
            <TableCell>Experiment</TableCell>
            <TableCell>Dataset</TableCell>
            <TableCell>Target</TableCell>
            <TableCell>Completed</TableCell>
            {metricNames.map((name) => (
              <TableCell key={name} align="right">
                {name}
              </TableCell>
            ))}
            <TableCell align="right">Links</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sorted.map((candidate, index) => (
            <TableRow key={candidate.training_job_id} hover>
              {rankMetric ? (
                <TableCell align="right">
                  {candidate.metrics[rankMetric] !== undefined ? index + 1 : '—'}
                </TableCell>
              ) : null}
              <TableCell>
                <Chip size="small" label={candidate.model_type} />
              </TableCell>
              <TableCell>{candidate.experiment_name}</TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {candidate.dataset_version ?? '—'}
                </Typography>
              </TableCell>
              <TableCell>{candidate.target_column ?? '—'}</TableCell>
              <TableCell>
                {candidate.completed_at ? new Date(candidate.completed_at).toLocaleString() : '—'}
              </TableCell>
              {metricNames.map((name) => {
                const value = candidate.metrics[name];
                const isBest = bestJobIdByMetric.get(name) === candidate.training_job_id;
                return (
                  <TableCell
                    key={name}
                    align="right"
                    sx={isBest ? { fontWeight: 700, color: 'success.main' } : undefined}
                  >
                    {formatValue(value)}
                  </TableCell>
                );
              })}
              <TableCell align="right">
                <Stack direction="row" spacing={0.25} justifyContent="flex-end">
                  <Tooltip title="View full evaluation detail">
                    <IconButton
                      size="small"
                      aria-label={`View details for ${candidate.model_type}`}
                      onClick={() => onOpenDetail(candidate)}
                    >
                      <InfoOutlinedIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Open experiment">
                    <IconButton
                      size="small"
                      component={Link}
                      href={`/experiments/${candidate.experiment_id}` as Route}
                      target="_blank"
                      aria-label={`Open experiment ${candidate.experiment_name}`}
                    >
                      <ScienceIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Open training job">
                    <IconButton
                      size="small"
                      component={Link}
                      href={`/ml/training?jobId=${candidate.training_job_id}` as Route}
                      target="_blank"
                      aria-label={`Open training job ${candidate.training_job_id}`}
                    >
                      <SmartToyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  {candidate.model_artifact_url ? (
                    <Tooltip title="Download model artifact">
                      <IconButton
                        size="small"
                        component="a"
                        href={`${env.NEXT_PUBLIC_API_URL}${candidate.model_artifact_url}`}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Download model artifact for ${candidate.model_type}`}
                      >
                        <DownloadIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  ) : null}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
