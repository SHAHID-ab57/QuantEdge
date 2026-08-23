'use client';

import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { type ChangeEvent, type ReactNode } from 'react';

export type TradeSideFilter = 'all' | 'buy' | 'sell';

export interface TradeTapeFiltersProps {
  side: TradeSideFilter;
  onSideChange: (side: TradeSideFilter) => void;
  /** Minimum quantity to display; `0` shows everything. */
  minSize: number;
  onMinSizeChange: (minSize: number) => void;
  /** How many rows survive the current filters, for the "showing N of M" readout. */
  visibleCount: number;
  totalCount: number;
  /** Rendered at the end of the row — the CSV export button. */
  action?: ReactNode;
}

const SIDE_OPTIONS: { value: TradeSideFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'buy', label: 'Buy' },
  { value: 'sell', label: 'Sell' },
];

/**
 * Filters applied to the trade tape's _display_ only — never to the
 * underlying session/rolling accumulators, which must keep seeing every
 * trade regardless of what the user is currently looking at (see
 * `useTradeAnalytics`). The "showing N of M" readout exists precisely so
 * that distinction is visible: a filtered tape is obviously a filtered
 * view, not a market that went quiet.
 *
 * Same `ToggleButtonGroup` pattern as `MaxRowsSelector`/`DepthSelector` for
 * the side filter, plus a numeric field for the minimum-size filter.
 */
export function TradeTapeFilters({
  side,
  onSideChange,
  minSize,
  onMinSizeChange,
  visibleCount,
  totalCount,
  action,
}: TradeTapeFiltersProps) {
  function handleMinSizeChange(event: ChangeEvent<HTMLInputElement>) {
    const parsed = Number(event.target.value);
    onMinSizeChange(Number.isFinite(parsed) && parsed >= 0 ? parsed : 0);
  }

  const filtered = visibleCount !== totalCount;

  return (
    <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
      <ToggleButtonGroup
        value={side}
        exclusive
        size="small"
        onChange={(_, next: TradeSideFilter | null) => {
          if (next !== null) {
            onSideChange(next);
          }
        }}
        aria-label="Filter the trade tape by side"
      >
        {SIDE_OPTIONS.map((option) => (
          <ToggleButton
            key={option.value}
            value={option.value}
            aria-label={`Show ${option.label} trades`}
          >
            {option.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <TextField
        size="small"
        type="number"
        label="Min. size"
        value={minSize === 0 ? '' : minSize}
        onChange={handleMinSizeChange}
        placeholder="0"
        slotProps={{
          htmlInput: { min: 0, step: 'any', 'aria-label': 'Minimum trade size' },
          input: {
            startAdornment: <InputAdornment position="start">≥</InputAdornment>,
          },
        }}
        sx={{ width: 128 }}
      />
      <Typography
        variant="caption"
        color={filtered ? 'warning.main' : 'text.secondary'}
        role="status"
        aria-label="Trade tape filter result"
        sx={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {filtered
          ? `Showing ${visibleCount} of ${totalCount} rows`
          : `Showing all ${totalCount} rows`}
      </Typography>
      <Stack sx={{ ml: 'auto' }}>{action}</Stack>
    </Stack>
  );
}
