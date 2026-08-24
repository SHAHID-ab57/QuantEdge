'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';
import type { CandlestickData, HistogramData, UTCTimestamp } from 'lightweight-charts';
import { useCallback, useMemo, useState } from 'react';
import type { Market } from '@/types/api/market';
import {
  CandlestickChart,
  type CrosshairPoint,
  type OverlaySeriesInput,
} from './candlestick-chart';
import { ChartLegend, type ChartLegendPoint } from './chart-legend';
import { ChartToolbar } from './chart-toolbar';
import { toChartSeries } from './data-adapter';
import { useChartCandles } from './hooks/use-chart-candles';

export interface ChartContainerProps {
  symbol: string | null;
  timeframe: string | null;
  start?: string | null;
  end?: string | null;
  height?: number;
  markets?: Market[];
  availableTimeframes?: string[];
  onSymbolChange?: (symbol: string) => void;
  onTimeframeChange?: (timeframe: string) => void;
  /** See `CandlestickChartProps.liveCandle` — passed straight through. */
  liveCandle?: CandlestickData | null;
  liveVolume?: HistogramData | null;
  /** See `CandlestickChartProps.overlays` — passed straight through. */
  overlays?: OverlaySeriesInput[];
}

function ChartSkeleton({ height }: { height: number }) {
  return (
    <Stack spacing={1} role="status" aria-label="Loading chart">
      <Skeleton variant="rounded" height={40} width={320} />
      <Skeleton variant="rounded" height={height} />
    </Stack>
  );
}

/**
 * The reusable chart module's entry point: wires data fetching
 * (`useChartCandles`), the API→chart transform (`toChartSeries`), and the
 * presentational pieces (`ChartToolbar`, `ChartLegend`, `CandlestickChart`)
 * together, handling every state Objective #11 calls out — loading, empty,
 * API failure, and (via `toChartSeries`) unexpected data. See
 * `FRONTEND.md` § "Chart module" for the full data-flow diagram.
 */
export function ChartContainer({
  symbol,
  timeframe,
  start,
  end,
  height = 480,
  markets,
  availableTimeframes,
  onSymbolChange,
  onTimeframeChange,
  liveCandle = null,
  liveVolume = null,
  overlays = [],
}: ChartContainerProps) {
  const theme = useTheme();
  const [crosshair, setCrosshair] = useState<CrosshairPoint | null>(null);
  const query = useChartCandles({ symbol, timeframe, start, end });

  const series = useMemo(
    () =>
      toChartSeries(query.data?.candles ?? [], {
        upColor: theme.palette.success.main,
        downColor: theme.palette.error.main,
      }),
    [query.data?.candles, theme.palette.success.main, theme.palette.error.main],
  );

  // CandlestickChart has no imperative handle; bumping this token is what
  // its `fitContentToken` prop watches to re-fit on demand (Objective #5).
  const [fitContentToken, setFitContentToken] = useState(0);
  const handleFitContent = useCallback(() => {
    setFitContentToken((token) => token + 1);
  }, []);

  const legendPoint: ChartLegendPoint | null = useMemo(() => {
    if (crosshair) {
      return crosshair;
    }
    // A live forming bar is more current than the last historical candle.
    const last = liveCandle ?? series.candlesticks.at(-1);
    if (!last) {
      return null;
    }
    const lastVolume = liveVolume ?? series.volume.at(-1);
    return {
      time: last.time as UTCTimestamp,
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
      volume: lastVolume?.value ?? null,
    };
  }, [crosshair, series, liveCandle, liveVolume]);

  if (!symbol || !timeframe) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="body1" color="text.secondary">
          Select a market and timeframe to view the candlestick chart.
        </Typography>
      </Paper>
    );
  }

  if (query.isLoading) {
    return <ChartSkeleton height={height} />;
  }

  if (query.isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button onClick={() => query.refetch()} size="small">
            Retry
          </Button>
        }
      >
        Failed to load chart data: {query.error.message}
      </Alert>
    );
  }

  if (series.candlesticks.length === 0 && !liveCandle) {
    return (
      <Alert severity="info" role="status" aria-label="No chart data">
        No candles found for {symbol} on the {timeframe} timeframe in this range.
      </Alert>
    );
  }

  return (
    <Stack spacing={1}>
      <ChartToolbar
        symbol={symbol}
        timeframe={timeframe}
        onFitContent={handleFitContent}
        candleCount={series.candlesticks.length}
        truncated={query.data?.truncated ?? false}
        markets={markets}
        availableTimeframes={availableTimeframes}
        onSymbolChange={onSymbolChange}
        onTimeframeChange={onTimeframeChange}
      />
      <CandlestickChart
        candlesticks={series.candlesticks}
        volume={series.volume}
        onCrosshairMove={setCrosshair}
        fitContentToken={fitContentToken}
        liveCandle={liveCandle}
        liveVolume={liveVolume}
        overlays={overlays}
        height={height}
      />
      <ChartLegend point={legendPoint} />
    </Stack>
  );
}
