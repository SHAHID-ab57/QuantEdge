'use client';

import FastForwardIcon from '@mui/icons-material/FastForward';
import FastRewindIcon from '@mui/icons-material/FastRewind';
import FirstPageIcon from '@mui/icons-material/FirstPage';
import LastPageIcon from '@mui/icons-material/LastPage';
import IconButton from '@mui/material/IconButton';
import Slider from '@mui/material/Slider';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo, type SyntheticEvent } from 'react';
import { formatDuration } from '../engine/replay-format';
import type { ReplayTimeline as ReplayTimelineData } from '../engine/replay-timeline';

export interface ReplayTimelineProps {
  timeline: ReplayTimelineData;
  disabled: boolean;
  onSeekToProgress: (percent: number) => void;
  onJumpBack: () => void;
  onJumpForward: () => void;
  onJumpToStart: () => void;
  onJumpToEnd: () => void;
  /** How many candles a jump button moves — shown in its tooltip. */
  jumpSize: number;
}

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'medium',
});

function formatTime(ms: number | null): string {
  return ms === null ? '—' : timeFormatter.format(new Date(ms));
}

function elapsedMs(timeline: ReplayTimelineData): number | null {
  if (timeline.startMs === null || timeline.currentMs === null) {
    return null;
  }
  return timeline.currentMs - timeline.startMs;
}

function remainingMs(timeline: ReplayTimelineData): number | null {
  if (timeline.endMs === null || timeline.currentMs === null) {
    return null;
  }
  return timeline.endMs - timeline.currentMs;
}

/**
 * Start/current/end timestamps, elapsed/remaining duration across the
 * loaded data's own time span (not wall-clock playback time — see
 * `ReplayStatus`'s "Est. Completion" for that), a progress percentage, a
 * draggable seek slider, jump-to-start/end, and ±`jumpSize`-candle jump
 * buttons. The slider's value is a `[0, 100]` percentage
 * (`replay-timeline.ts`'s `computeTimeline`/`indexForProgress` are the
 * pure conversions either direction) rather than a raw candle index, so
 * its scale stays meaningful regardless of how many candles are actually
 * loaded. `valueLabelDisplay="auto"` surfaces the percentage right on the
 * thumb while dragging, rather than only in the caption above.
 */
function ReplayTimelineInner({
  timeline,
  disabled,
  onSeekToProgress,
  onJumpBack,
  onJumpForward,
  onJumpToStart,
  onJumpToEnd,
  jumpSize,
}: ReplayTimelineProps) {
  const handleSliderChange = (_: Event | SyntheticEvent, value: number | number[]) => {
    onSeekToProgress(Array.isArray(value) ? (value[0] ?? 0) : value);
  };

  return (
    <Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="caption" color="text.secondary">
          Start: {formatTime(timeline.startMs)}
        </Typography>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          {formatTime(timeline.currentMs)} · {timeline.progress.toFixed(1)}% · candle{' '}
          {timeline.position} of {timeline.totalCandles}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          End: {formatTime(timeline.endMs)}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center">
        <Tooltip title="Jump to the first candle (Home)">
          <span>
            <IconButton
              onClick={onJumpToStart}
              disabled={disabled}
              aria-label="Jump to start"
              size="small"
            >
              <FirstPageIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title={`Back ${jumpSize} candles`}>
          <span>
            <IconButton
              onClick={onJumpBack}
              disabled={disabled}
              aria-label={`Jump back ${jumpSize} candles`}
              size="small"
            >
              <FastRewindIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Slider
          value={timeline.progress}
          onChange={handleSliderChange}
          disabled={disabled}
          min={0}
          max={100}
          size="small"
          aria-label="Replay progress"
          valueLabelDisplay="auto"
          valueLabelFormat={(value) => `${value.toFixed(0)}%`}
          sx={{ flexGrow: 1 }}
        />
        <Tooltip title={`Forward ${jumpSize} candles`}>
          <span>
            <IconButton
              onClick={onJumpForward}
              disabled={disabled}
              aria-label={`Jump forward ${jumpSize} candles`}
              size="small"
            >
              <FastForwardIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Jump to the last candle (End)">
          <span>
            <IconButton
              onClick={onJumpToEnd}
              disabled={disabled}
              aria-label="Jump to end"
              size="small"
            >
              <LastPageIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
      <Stack direction="row" spacing={3}>
        <Typography variant="caption" color="text.secondary">
          Elapsed: {formatDuration(elapsedMs(timeline))}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Remaining: {formatDuration(remainingMs(timeline))}
        </Typography>
      </Stack>
    </Stack>
  );
}

export const ReplayTimeline = memo(ReplayTimelineInner);
