'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { ConfirmActionDialog } from '@/components/confirm-action-dialog';
import type { RiskSummary } from '@/types/api/paper-trading';

export interface RiskSummaryPanelProps {
  data: RiskSummary | undefined;
  isLoading: boolean;
  onResume: () => void;
  resuming: boolean;
  resumeError: string | null;
}

function LimitRow({
  label,
  currentPct,
  maxPct,
}: {
  label: string;
  currentPct: number;
  maxPct: number;
}) {
  const ratio = maxPct > 0 ? Math.min(Math.max(currentPct / maxPct, 0), 1) : 0;
  const overLimit = currentPct > maxPct;

  let progressColor: 'error' | 'warning' | 'primary' = 'primary';
  if (overLimit) {
    progressColor = 'error';
  } else if (ratio > 0.8) {
    progressColor = 'warning';
  }
  return (
    <Stack spacing={0.5}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="body2">{label}</Typography>
        <Typography variant="body2" color={overLimit ? 'error.main' : 'text.secondary'}>
          {currentPct.toFixed(2)}% / {maxPct.toFixed(2)}% limit
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={ratio * 100}
        color={progressColor}
        aria-label={`${label} usage`}
      />
    </Stack>
  );
}

/**
 * An account's own current exposure and drawdown against its configured
 * pre-trade risk limits (`GET .../risk`, polled every 10s — the same
 * cadence the summary/positions already poll at, since both depend on
 * live prices and the account's own running balance moving on their
 * own). When trading is halted, "Resume Trading" is the *only* way to
 * clear it (this feature's own spec: no self-healing on balance
 * recovery) — guarded by the same `ConfirmActionDialog` "are you sure"
 * pattern every other consequential action on this page already uses.
 */
export function RiskSummaryPanel({
  data,
  isLoading,
  onResume,
  resuming,
  resumeError,
}: RiskSummaryPanelProps) {
  const [confirming, setConfirming] = useState(false);

  if (isLoading || !data) {
    return (
      <Stack spacing={1}>
        <Skeleton variant="text" width={200} />
        <Skeleton variant="rectangular" height={8} />
        <Skeleton variant="text" width={200} />
        <Skeleton variant="rectangular" height={8} />
      </Stack>
    );
  }

  const currentExposurePct = Number(data.current_exposure_pct);
  const maxExposurePct = Number(data.max_exposure_pct);
  const currentDrawdownPct = Number(data.current_drawdown_pct);
  const maxDrawdownPct = Number(data.max_drawdown_pct);

  return (
    <Stack spacing={2}>
      {data.trading_halted ? (
        <Alert
          severity="error"
          role="alert"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => setConfirming(true)}
              disabled={resuming}
            >
              {resuming ? 'Resuming…' : 'Resume Trading'}
            </Button>
          }
        >
          Trading halted — balance has fallen more than {Number(data.max_drawdown_pct).toFixed(0)}%
          below its peak of ${Number(data.peak_balance).toFixed(2)}.
        </Alert>
      ) : (
        <Chip
          size="small"
          color="success"
          label="Trading active"
          sx={{ alignSelf: 'flex-start' }}
        />
      )}

      {resumeError ? (
        <Alert severity="error" role="alert">
          {resumeError}
        </Alert>
      ) : null}

      <LimitRow label="Exposure" currentPct={currentExposurePct} maxPct={maxExposurePct} />
      <LimitRow label="Drawdown" currentPct={currentDrawdownPct} maxPct={maxDrawdownPct} />

      <Typography variant="caption" color="text.secondary">
        Max position size per symbol: {Number(data.max_position_size_pct).toFixed(2)}% of balance
      </Typography>

      <ConfirmActionDialog
        open={confirming}
        title="Resume trading?"
        description="Clears this account's drawdown halt so new orders can be placed again, and resets the peak balance to the current balance so drawdown is measured fresh from now on."
        confirmLabel="Resume Trading"
        busyLabel="Resuming…"
        color="primary"
        busy={resuming}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          onResume();
        }}
      />
    </Stack>
  );
}
