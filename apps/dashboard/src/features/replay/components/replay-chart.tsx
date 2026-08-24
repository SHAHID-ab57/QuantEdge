'use client';

import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import { useTheme } from '@mui/material/styles';
import type { UTCTimestamp } from 'lightweight-charts';
import { memo, useMemo } from 'react';
import { CandlestickChart, type OverlaySeriesInput } from '@/components/chart/candlestick-chart';
import { ChartLegend, type ChartLegendPoint } from '@/components/chart/chart-legend';
import type { Candle } from '@/types/api/market';
import type { ReplayClockTick } from '../engine/replay-clock';
import { useReplayChartSync } from '../hooks/use-replay-chart-sync';

export interface ReplayChartProps {
  candles: Candle[];
  /** The synchronized position to render — see `engine/replay-clock.ts`. */
  tick: ReplayClockTick;
  isLoading: boolean;
  /**
   * Indicator overlays calculated once over the *entire* loaded session
   * (the same "compute once up front" contract `candles` already
   * follows) — each one's `data` is revealed only up to `tick.index`
   * below, so an overlay never shows a researcher a value from beyond the
   * current replay position.
   */
  overlays?: OverlaySeriesInput[];
  height?: number;
}

/**
 * Reuses `CandlestickChart` (the same primitive the History page and Live
 * Market Dashboard render) and `ChartLegend` unmodified — see
 * `hooks/use-replay-chart-sync.ts` for how replay state becomes that
 * component's existing `candlesticks`/`liveCandle` props. This wrapper adds
 * no chart logic of its own; it only supplies the theme colors and the
 * legend's current-point readout.
 *
 * Reads its position from a `ReplayClockTick` rather than being handed
 * `currentIndex`/`revealEpoch` directly — the same tick any other future
 * replay-synchronized module would read from the identical `ReplayClock`
 * instance, guaranteeing this chart can never drift out of sync with them.
 * `React.memo`-wrapped for consistency with the rest of this feature's
 * components; since `tick` changes on every playback step by design, this
 * does re-render every tick — correctly, since the chart genuinely has new
 * data to show.
 */
function ReplayChartInner({
  candles,
  tick,
  isLoading,
  overlays = [],
  height = 420,
}: ReplayChartProps) {
  const theme = useTheme();
  const chartTheme = useMemo(
    () => ({ upColor: theme.palette.success.main, downColor: theme.palette.error.main }),
    [theme.palette.success.main, theme.palette.error.main],
  );
  const sync = useReplayChartSync(candles, tick.index, tick.revealEpoch, chartTheme);

  // Reveal each overlay's line only up to the current replay position,
  // mirroring exactly how `useReplayChartSync` reveals `candles` above —
  // an overlay was calculated once over the whole session, but must never
  // show a value from beyond "now" in the replay.
  const revealedOverlays = useMemo(
    () => overlays.map((overlay) => ({ ...overlay, data: overlay.data.slice(0, tick.index + 1) })),
    [overlays, tick.index],
  );

  const legendPoint: ChartLegendPoint | null = useMemo(() => {
    const bar = sync.liveCandle ?? sync.candlesticks.at(-1);
    if (!bar) {
      return null;
    }
    const volumeBar = sync.liveVolume ?? sync.volume.at(-1);
    return {
      time: bar.time as UTCTimestamp,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: volumeBar?.value ?? null,
    };
  }, [sync]);

  if (isLoading) {
    return (
      <Stack spacing={1} role="status" aria-label="Loading replay chart">
        <Skeleton variant="rounded" height={height} />
      </Stack>
    );
  }

  return (
    <Stack spacing={1}>
      <CandlestickChart
        candlesticks={sync.candlesticks}
        volume={sync.volume}
        liveCandle={sync.liveCandle}
        liveVolume={sync.liveVolume}
        overlays={revealedOverlays}
        height={height}
      />
      <ChartLegend point={legendPoint} />
    </Stack>
  );
}

export const ReplayChart = memo(ReplayChartInner);
