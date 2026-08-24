'use client';

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import { memo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatNumber } from '@/features/markets/lib/format';
import { estimateCompletionMs, formatDuration } from '../engine/replay-format';
import { tickIntervalMs, type ReplaySpeed } from '../engine/replay-speed';
import type { ReplayPhase } from '../engine/replay-state-machine';
import type { ReplayTimeline } from '../engine/replay-timeline';

export interface ReplayStatusProps {
  phase: ReplayPhase;
  error: string | null;
  truncated: boolean;
  onRetry: () => void;
  timeline: ReplayTimeline;
  speed: ReplaySpeed;
}

const PHASE_LABEL: Record<ReplayPhase, string> = {
  idle: 'Idle',
  loading: 'Loading…',
  playing: 'Playing',
  paused: 'Paused',
  seeking: 'Seeking…',
  completed: 'Completed',
  error: 'Error',
};

const PHASE_COLOR: Record<ReplayPhase, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  idle: 'default',
  loading: 'info',
  playing: 'success',
  paused: 'warning',
  seeking: 'info',
  completed: 'default',
  error: 'error',
};

const UNAVAILABLE = 'Unavailable';

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

function formatReplayTime(ms: number | null): string {
  return ms === null ? UNAVAILABLE : dateTimeFormatter.format(new Date(ms));
}

/**
 * The replay session's status at a glance: phase, replay time (the current
 * candle's own timestamp — not wall-clock "now"), position within the
 * loaded set, how many candles remain, playback speed, and an estimated
 * time to completion at that speed — plus the error/retry and truncation
 * notices this component already covered. Built entirely from `StatTile`
 * (`@/components/stat-tile`, already shared with the Trade Analytics and
 * Live Market dashboards) rather than ad-hoc `Typography`, so this panel's
 * spacing/typography matches the rest of the platform without
 * reintroducing a fourth local "label + value" tile.
 *
 * `phase`/`timeline`/`speed` drive every other figure from a single
 * lookup table or pure calculation (`estimateCompletionMs`,
 * `formatDuration`) — a new `ReplayPhase` is a TypeScript error here if
 * its label/color entry is missing, not a silent gap.
 */
function ReplayStatusInner({
  phase,
  error,
  truncated,
  onRetry,
  timeline,
  speed,
}: ReplayStatusProps) {
  const hasSession = timeline.totalCandles > 0;
  const remainingCandles = Math.max(timeline.totalCandles - timeline.position, 0);
  const etaMs = hasSession ? estimateCompletionMs(remainingCandles, tickIntervalMs(speed)) : null;
  const isActivelyCounting = phase === 'playing' || phase === 'paused';

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Chip
          label={PHASE_LABEL[phase]}
          color={PHASE_COLOR[phase]}
          size="small"
          sx={{ fontWeight: 700 }}
        />
        {phase === 'loading' ? (
          <Skeleton variant="text" width={160} role="status" aria-label="Loading replay session" />
        ) : null}
      </Stack>

      {hasSession ? (
        <Box
          sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 3 }, alignItems: 'center' }}
          role="status"
          aria-label="Replay status"
        >
          <StatTile
            label="Replay Time"
            value={formatReplayTime(timeline.currentMs)}
            emphasis
            hint="The timestamp of the candle currently on screen — not the current real-world time."
          />
          <StatTile
            label="Current Candle"
            value={`${formatNumber(timeline.position)} of ${formatNumber(timeline.totalCandles)}`}
            hint="Position within the loaded session."
          />
          <StatTile
            label="Loaded Candles"
            value={formatNumber(timeline.totalCandles)}
            hint="Every candle in this session was fetched once, up front — no further request happens as replay advances."
          />
          <StatTile
            label="Remaining Candles"
            value={formatNumber(remainingCandles)}
            hint="Candles between the current position and the end of the loaded session."
          />
          <StatTile
            label="Replay Speed"
            value={`${speed}x`}
            hint="Candles advance faster or slower, not simulated market time — see the speed control."
          />
          <StatTile
            label="Est. Completion"
            value={isActivelyCounting ? formatDuration(etaMs) : UNAVAILABLE}
            color={remainingCandles === 0 ? 'success.main' : undefined}
            hint="How long the remaining candles would take to finish at the current speed if playing continuously."
          />
        </Box>
      ) : null}

      {phase === 'error' && error ? (
        <Alert
          severity="error"
          role="alert"
          action={
            <Button size="small" onClick={onRetry}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      ) : null}
      {truncated ? (
        <Alert severity="warning" role="status">
          This session was cut off before the full range loaded — narrow the date range or choose a
          coarser timeframe to replay it in full.
        </Alert>
      ) : null}
    </Stack>
  );
}

export const ReplayStatus = memo(ReplayStatusInner);
