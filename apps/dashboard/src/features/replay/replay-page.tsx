'use client';

import KeyboardIcon from '@mui/icons-material/Keyboard';
import Alert from '@mui/material/Alert';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useCallback, useMemo, useState } from 'react';
import { Section } from '@/components/section';
import { ReplayChart } from './components/replay-chart';
import { ReplayConfigForm, type ReplayConfigFormValues } from './components/replay-config-form';
import { ReplayControls } from './components/replay-controls';
import { ReplayStatus } from './components/replay-status';
import { ReplayTimeline } from './components/replay-timeline';
import {
  useReplayCandles,
  replayConfigKey,
  type ReplaySessionConfig,
} from './hooks/use-replay-candles';
import { useReplayClockTick } from './hooks/use-replay-clock';
import { useReplayEngine } from './hooks/use-replay-engine';
import { useReplayKeyboardShortcuts } from './hooks/use-replay-keyboard-shortcuts';

/** How many candles the ±jump buttons move (distinct from Home/End, which jump to the very first/last candle). */
const JUMP_SIZE = 20;

const KEYBOARD_SHORTCUTS_HINT =
  'Space: Play/Pause · ←/→: Previous/Next candle · Home/End: Jump to start/end · +/-: Speed up/down';

function toIsoUtc(datetimeLocal: string): string {
  // datetime-local has no timezone; interpreted as the browser's local
  // time, matching how the input itself renders it back to the user.
  return new Date(datetimeLocal).toISOString();
}

function toSessionConfig(values: ReplayConfigFormValues): ReplaySessionConfig {
  return {
    symbol: values.market,
    timeframe: values.timeframe,
    start: toIsoUtc(values.start),
    end: toIsoUtc(values.end),
  };
}

/**
 * The Historical Market Replay Engine's page: configure a session, load its
 * candles once up front, then step or auto-play through them at a chosen
 * speed. Every piece of actual replay logic — the state machine, the
 * scheduler, the timeline math, and the cross-module `ReplayClock` — lives
 * in `engine/` with no React dependency and is unit-tested in isolation;
 * this component only wires that engine to a config form, a status panel,
 * and the reused candlestick chart. See `FRONTEND.md` § "Historical Market
 * Replay Engine" for the full architecture writeup, including the clock's
 * role as the synchronization backbone future modules (Trade Tape, Order
 * Book, indicators, AI prediction playback, paper trading, backtesting)
 * would subscribe to (`extension-points.ts`), and why trade- and order-
 * book-level replay aren't implemented today.
 *
 * Layout is ordered by visual weight: session configuration, then the
 * status panel (the entry point for "what is replay doing right now"),
 * then the chart, then transport controls and the timeline together
 * (they are one interaction, not two).
 */
export function ReplayPage() {
  const [config, setConfig] = useState<ReplaySessionConfig | null>(null);
  const candlesQuery = useReplayCandles(config);

  const requestId = config ? replayConfigKey(config) : null;
  const status = useMemo(
    () => ({
      requestId,
      isLoading: candlesQuery.isLoading,
      isError: candlesQuery.isError,
      errorMessage: candlesQuery.error?.message ?? null,
      candles: candlesQuery.data?.candles,
    }),
    [
      requestId,
      candlesQuery.isLoading,
      candlesQuery.isError,
      candlesQuery.error,
      candlesQuery.data,
    ],
  );

  const engine = useReplayEngine(status);
  // The chart (and, in the future, any other replay-synchronized module)
  // reads its position from the centralized clock rather than directly
  // from `engine.currentIndex`/`engine.revealEpoch` — see `use-replay-clock.ts`.
  const clockTick = useReplayClockTick(engine.clock);

  const handleConfigSubmitted = useCallback((values: ReplayConfigFormValues) => {
    setConfig(toSessionConfig(values));
  }, []);

  const handleRetry = useCallback(() => {
    candlesQuery.refetch();
  }, [candlesQuery]);

  const handleJumpBack = useCallback(() => {
    engine.seekToIndex(engine.currentIndex - JUMP_SIZE);
  }, [engine]);

  const handleJumpForward = useCallback(() => {
    engine.seekToIndex(engine.currentIndex + JUMP_SIZE);
  }, [engine]);

  const handleJumpToStart = useCallback(() => {
    engine.seekToIndex(0);
  }, [engine]);

  const handleJumpToEnd = useCallback(() => {
    engine.seekToIndex(engine.candleCount - 1);
  }, [engine]);

  const hasSession = engine.phase !== 'idle';
  const isChartLoading = engine.phase === 'loading';
  const controlsDisabled =
    engine.phase === 'idle' || engine.phase === 'loading' || engine.phase === 'error';

  useReplayKeyboardShortcuts({
    enabled: !controlsDisabled,
    phase: engine.phase,
    speed: engine.speed,
    candleCount: engine.candleCount,
    play: engine.play,
    resume: engine.resume,
    pause: engine.pause,
    next: engine.next,
    previous: engine.previous,
    seekToIndex: engine.seekToIndex,
    setSpeed: engine.setSpeed,
  });

  return (
    <Stack spacing={2}>
      <Section title="Replay Session" subtitle="Market, timeframe, and date range to replay">
        <ReplayConfigForm
          onSubmitted={handleConfigSubmitted}
          disabled={engine.phase === 'loading'}
        />
      </Section>

      {!hasSession ? (
        <Alert severity="info" role="status">
          Configure a market, timeframe, and date range above, then load a session to begin
          replaying historical candles.
        </Alert>
      ) : (
        <>
          <Section title="Status" subtitle="What replay is doing right now">
            <ReplayStatus
              phase={engine.phase}
              error={engine.error}
              truncated={candlesQuery.data?.truncated ?? false}
              onRetry={handleRetry}
              timeline={engine.timeline}
              speed={engine.speed}
            />
          </Section>

          <Section title="Chart" subtitle="Reuses the platform's candlestick chart module">
            <ReplayChart candles={engine.candles} tick={clockTick} isLoading={isChartLoading} />
          </Section>

          <Section
            title="Controls"
            action={
              <Tooltip title={KEYBOARD_SHORTCUTS_HINT}>
                <IconButton size="small" aria-label="Keyboard shortcuts">
                  <KeyboardIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            }
          >
            <Stack spacing={2}>
              <ReplayControls
                phase={engine.phase}
                speed={engine.speed}
                onPlay={engine.play}
                onResume={engine.resume}
                onPause={engine.pause}
                onStop={engine.stop}
                onRestart={engine.restart}
                onNext={engine.next}
                onPrevious={engine.previous}
                onSpeedChange={engine.setSpeed}
              />
              <ReplayTimeline
                timeline={engine.timeline}
                disabled={controlsDisabled}
                onSeekToProgress={engine.seekToProgress}
                onJumpBack={handleJumpBack}
                onJumpForward={handleJumpForward}
                onJumpToStart={handleJumpToStart}
                onJumpToEnd={handleJumpToEnd}
                jumpSize={JUMP_SIZE}
              />
            </Stack>
          </Section>

          {engine.currentCandle ? (
            <Typography variant="caption" color="text.secondary">
              Candle source: {engine.currentCandle.source}
            </Typography>
          ) : null}
        </>
      )}
    </Stack>
  );
}
