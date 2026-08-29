'use client';

import DownloadIcon from '@mui/icons-material/Download';
import ScienceIcon from '@mui/icons-material/Science';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { Route } from 'next';
import Link from 'next/link';
import { env } from '@/config/env';
import { EvaluationSummary } from '@/features/ml-training/components/evaluation-summary';
import type { BenchmarkCandidate } from '@/types/api/evaluation';
import { DatasetSummaryCard } from './dataset-summary-card';
import { toModelKind } from '../lib/model-kind';

export interface CandidateDetailDialogProps {
  candidate: BenchmarkCandidate | null;
  onClose: () => void;
}

/**
 * One benchmark candidate's full detail: the Dataset Summary Card, then
 * `EvaluationSummary` — the exact component `/ml/training`'s own job detail
 * dialog already uses (confusion matrix, ROC/PR curves, feature importance,
 * prediction samples, model metadata) — reused verbatim against this
 * candidate's own `report` (its training job's `result_summary`, returned
 * unchanged by the benchmark API), so nothing here is recomputed. Deep
 * links to the Experiment, the Training Job, and the downloadable Model
 * Artifact sit in the header, resolving to routes/downloads this platform
 * already serves.
 */
export function CandidateDetailDialog({ candidate, onClose }: CandidateDetailDialogProps) {
  if (!candidate) return null;

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip size="small" label={candidate.model_type} />
          <Typography variant="body2" color="text.secondary" component="span">
            {candidate.experiment_name}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              size="small"
              variant="outlined"
              startIcon={<ScienceIcon fontSize="small" />}
              component={Link}
              href={`/experiments/${candidate.experiment_id}` as Route}
              target="_blank"
            >
              Open Experiment
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<SmartToyIcon fontSize="small" />}
              component={Link}
              href={`/ml/training?jobId=${candidate.training_job_id}` as Route}
              target="_blank"
            >
              Open Training Job
            </Button>
            {candidate.model_artifact_url ? (
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon fontSize="small" />}
                component="a"
                href={`${env.NEXT_PUBLIC_API_URL}${candidate.model_artifact_url}`}
                target="_blank"
                rel="noreferrer"
              >
                Download Model Artifact
              </Button>
            ) : null}
          </Stack>
          <DatasetSummaryCard candidate={candidate} />
          <EvaluationSummary
            modelKind={toModelKind(candidate.model_kind)}
            metrics={candidate.metrics}
            summary={candidate.report ?? {}}
          />
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
