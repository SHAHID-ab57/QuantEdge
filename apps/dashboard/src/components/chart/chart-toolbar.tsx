'use client';

import FitScreenIcon from '@mui/icons-material/FitScreen';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { Market } from '@/types/api/market';
import { MarketSelector } from './market-selector';
import { TimeframeSelector } from './timeframe-selector';

export interface ChartToolbarProps {
  symbol: string;
  timeframe: string;
  onFitContent: () => void;
  candleCount: number;
  truncated: boolean;
  /**
   * Supplying these three switches the toolbar into "standalone" mode and
   * renders its own `MarketSelector`/`TimeframeSelector`. Omit them when an
   * existing filter UI (e.g. the History explorer's form) already owns
   * market/timeframe selection, so the chart never duplicates it.
   */
  markets?: Market[];
  availableTimeframes?: string[];
  onSymbolChange?: (symbol: string) => void;
  onTimeframeChange?: (timeframe: string) => void;
}

export function ChartToolbar({
  symbol,
  timeframe,
  onFitContent,
  candleCount,
  truncated,
  markets,
  availableTimeframes,
  onSymbolChange,
  onTimeframeChange,
}: ChartToolbarProps) {
  const standalone = Boolean(markets && onSymbolChange && availableTimeframes && onTimeframeChange);

  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="center"
      flexWrap="wrap"
      sx={{ rowGap: 1 }}
      role="toolbar"
      aria-label="Chart controls"
    >
      {standalone ? (
        <>
          <MarketSelector markets={markets!} value={symbol} onChange={onSymbolChange!} />
          <TimeframeSelector
            timeframes={availableTimeframes!}
            value={timeframe}
            onChange={onTimeframeChange!}
          />
        </>
      ) : (
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          {symbol} · {timeframe}
        </Typography>
      )}

      <Tooltip title="Fit all candles in view">
        <IconButton size="small" aria-label="Fit chart to content" onClick={onFitContent}>
          <FitScreenIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
        {candleCount.toLocaleString()} candles
        {truncated ? ' (showing the most recent range — narrow the date range for more)' : ''}
      </Typography>
    </Stack>
  );
}
