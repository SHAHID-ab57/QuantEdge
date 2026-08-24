'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import type { IndicatorCalculation } from '@/types/api/indicators';
import type { IndicatorKnowledge } from '../lib/indicator-knowledge';
import { IndicatorResults } from './indicator-results';

export interface ResultsPanelProps {
  /** `false` before the researcher has ever pressed Calculate. */
  requested: boolean;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  result: IndicatorCalculation | undefined;
  /** Required whenever `result` is present — the panel that renders it needs it to size the chart and classify signals. */
  knowledge: IndicatorKnowledge | undefined;
  onRetry: () => void;
}

/**
 * Chooses between the four states the results area can be in: not yet
 * requested, calculating, failed, or a rendered result.
 *
 * Extracted from `IndicatorsPage` rather than inlined as chained ternaries
 * — the states are mutually exclusive and each has real content, so a flat
 * sequence of early returns reads far better than nesting them three deep.
 */
export function ResultsPanel({
  requested,
  isPending,
  isError,
  error,
  result,
  knowledge,
  onRetry,
}: ResultsPanelProps) {
  if (!requested) {
    return (
      <Alert severity="info" role="status">
        Choose a market, timeframe, and indicator above, then select Calculate to run it over stored
        candles.
      </Alert>
    );
  }

  if (isPending) {
    return (
      <Stack spacing={1} role="status" aria-label="Calculating indicator">
        <Skeleton variant="rounded" height={72} />
        <Skeleton variant="rounded" height={280} />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button size="small" onClick={onRetry}>
            Retry
          </Button>
        }
      >
        {error?.message ?? 'The calculation failed.'}
      </Alert>
    );
  }

  if (!result || !knowledge) {
    return null;
  }

  return <IndicatorResults result={result} knowledge={knowledge} />;
}
