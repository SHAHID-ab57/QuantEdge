'use client';

import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import NextLink from 'next/link';
import type { Route } from 'next';
import { InfoTooltip } from '@/components/info-tooltip';
import type { PredictionResponse } from '@/types/api/prediction';

export interface PredictionResultPanelProps {
  prediction: PredictionResponse;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ maxWidth: '65%' }}>
        {children}
      </Stack>
    </Stack>
  );
}

/**
 * One live prediction, framed so it can never read as a bare, certain
 * number: target and horizon lead (what is actually being predicted, and
 * how far ahead), then the predicted value itself, then confidence —
 * always shown as an explicit probability (0-100%), or, when this model
 * type has none, an explanation of why rather than a hidden field. Deep
 * links to the source Experiment/Training Job match the convention
 * `BenchmarkComparisonTable` already established.
 */
export function PredictionResultPanel({ prediction }: PredictionResultPanelProps) {
  return (
    <Stack
      spacing={1.25}
      sx={{ p: 2, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}
      aria-label="Prediction result"
    >
      <Row label="Target">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {prediction.target_column}
        </Typography>
      </Row>

      <Row label="Horizon">
        <Typography variant="body2">
          {prediction.horizon === null ? 'Not recorded' : `${prediction.horizon} candle(s) ahead`}
        </Typography>
      </Row>

      <Row label="As of">
        <Typography variant="body2">{new Date(prediction.as_of).toLocaleString()}</Typography>
      </Row>

      <Row label="Predicted value">
        <Typography variant="h6" component="span">
          {String(prediction.predicted_value)}
        </Typography>
      </Row>

      <Row label="Confidence">
        {prediction.confidence !== null ? (
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {(prediction.confidence * 100).toFixed(1)}% probability
            </Typography>
            <InfoTooltip
              label="Confidence"
              sections={[
                {
                  heading: 'What this is',
                  body: 'The predicted class’s own probability, as the model itself estimated it — a statistical likelihood, never a promise of correctness.',
                },
              ]}
            />
          </Stack>
        ) : (
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <Chip size="small" variant="outlined" label="Not available" />
            <InfoTooltip
              label="Confidence"
              sections={[
                {
                  heading: 'Why this is unavailable',
                  body:
                    prediction.confidence_unavailable_reason ??
                    'This model does not produce class probabilities.',
                },
              ]}
            />
          </Stack>
        )}
      </Row>

      {prediction.probabilities ? (
        <Stack spacing={0.5}>
          <Typography variant="caption" color="text.secondary">
            Every class’s own probability
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {Object.entries(prediction.probabilities).map(([label, probability]) => (
              <Chip
                key={label}
                size="small"
                variant={label === String(prediction.predicted_value) ? 'filled' : 'outlined'}
                color={label === String(prediction.predicted_value) ? 'primary' : 'default'}
                label={`${label}: ${(probability * 100).toFixed(1)}%`}
              />
            ))}
          </Stack>
        </Stack>
      ) : null}

      <Row label="Actual outcome">
        <Typography variant="body2" color="text.secondary">
          {prediction.actual_outcome === null
            ? 'Not graded yet'
            : String(prediction.actual_outcome)}
        </Typography>
      </Row>

      <Stack direction="row" spacing={2} sx={{ pt: 0.5 }}>
        <Link component={NextLink} href={`/experiments/${prediction.experiment_id}` as Route}>
          View experiment
        </Link>
        <Link
          component={NextLink}
          href={`/ml/training?jobId=${prediction.training_job_id}` as Route}
        >
          View training job
        </Link>
      </Stack>

      <Typography variant="caption" color="text.secondary">
        A probabilistic estimate, not financial advice — see the linked training job’s own metrics
        before acting on this.
      </Typography>
    </Stack>
  );
}
