'use client';

import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SkipPreviousIcon from '@mui/icons-material/SkipPrevious';
import StopIcon from '@mui/icons-material/Stop';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { REPLAY_SPEEDS, type ReplaySpeed } from '../engine/replay-speed';
import type { ReplayPhase } from '../engine/replay-state-machine';

export interface ReplayControlsProps {
  phase: ReplayPhase;
  speed: ReplaySpeed;
  onPlay: () => void;
  onResume: () => void;
  onPause: () => void;
  onStop: () => void;
  onRestart: () => void;
  onNext: () => void;
  onPrevious: () => void;
  onSpeedChange: (speed: ReplaySpeed) => void;
}

/**
 * Play/Pause/Resume/Stop/Restart/Next/Previous plus the speed selector,
 * grouped into two visually distinct clusters — transport (the primary
 * action, sized up and colour-emphasized) and speed (secondary, grouped
 * under its own label) — separated by a `Divider` rather than sitting in
 * one undifferentiated row of same-sized icon buttons. Every button's
 * `disabled` state is derived from `phase` so an invalid click can't
 * happen from the UI side (the reducer would no-op it anyway, but a
 * visibly-enabled button that does nothing reads as broken).
 *
 * "Play" and "Resume" render as a single toggling button (its label and
 * handler swap with `phase`) rather than two permanently-visible buttons —
 * they are never both meaningful at once (see `useReplayEngine`'s
 * `PLAY`/`RESUME` distinction: `PLAY` is also valid from `completed`,
 * restarting at zero; `RESUME` only continues from a pause). Every
 * tooltip names the matching keyboard shortcut (see
 * `hooks/use-replay-keyboard-shortcuts.ts`) so the two stay discoverable
 * together rather than the shortcuts being a hidden feature.
 */
function ReplayControlsInner({
  phase,
  speed,
  onPlay,
  onResume,
  onPause,
  onStop,
  onRestart,
  onNext,
  onPrevious,
  onSpeedChange,
}: ReplayControlsProps) {
  const isLoaded = phase !== 'idle' && phase !== 'loading' && phase !== 'error';
  const isPlaying = phase === 'playing';
  const canStep = phase === 'paused' || phase === 'completed';
  const canStop = phase === 'playing' || phase === 'paused' || phase === 'completed';
  const canRestart = canStop;

  return (
    <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Tooltip title="Previous candle (←)">
          <span>
            <IconButton
              onClick={onPrevious}
              disabled={!canStep}
              aria-label="Previous candle"
              size="small"
            >
              <SkipPreviousIcon />
            </IconButton>
          </span>
        </Tooltip>

        {isPlaying ? (
          <Tooltip title="Pause (Space)">
            <IconButton onClick={onPause} aria-label="Pause" color="primary" size="medium">
              <PauseIcon fontSize="large" />
            </IconButton>
          </Tooltip>
        ) : (
          <Tooltip title={phase === 'paused' ? 'Resume (Space)' : 'Play (Space)'}>
            <span>
              <IconButton
                onClick={phase === 'paused' ? onResume : onPlay}
                disabled={!isLoaded}
                aria-label={phase === 'paused' ? 'Resume' : 'Play'}
                color="primary"
                size="medium"
              >
                <PlayArrowIcon fontSize="large" />
              </IconButton>
            </span>
          </Tooltip>
        )}

        <Tooltip title="Next candle (→)">
          <span>
            <IconButton onClick={onNext} disabled={!canStep} aria-label="Next candle" size="small">
              <SkipNextIcon />
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Stop and reset to the first candle">
          <span>
            <IconButton onClick={onStop} disabled={!canStop} aria-label="Stop" size="small">
              <StopIcon />
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Restart from the beginning, keeping play/pause state">
          <span>
            <IconButton
              onClick={onRestart}
              disabled={!canRestart}
              aria-label="Restart"
              size="small"
            >
              <RestartAltIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />

      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
          Speed
        </Typography>
        <ToggleButtonGroup
          value={speed}
          exclusive
          size="small"
          onChange={(_, next: ReplaySpeed | null) => {
            if (next !== null) {
              onSpeedChange(next);
            }
          }}
          aria-label="Replay speed"
        >
          {REPLAY_SPEEDS.map((option) => (
            <Tooltip key={option} title={`Play at ${option}× speed`}>
              <ToggleButton value={option} aria-label={`${option}x speed`}>
                {option}x
              </ToggleButton>
            </Tooltip>
          ))}
        </ToggleButtonGroup>
      </Stack>
    </Stack>
  );
}

export const ReplayControls = memo(ReplayControlsInner);
