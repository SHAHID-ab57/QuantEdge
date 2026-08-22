'use client';

import Autocomplete from '@mui/material/Autocomplete';
import TextField from '@mui/material/TextField';
import type { Market } from '@/types/api/market';

export interface MarketSelectorProps {
  markets: Market[];
  value: string | null;
  onChange: (symbol: string) => void;
  loading?: boolean;
  size?: 'small' | 'medium';
}

/**
 * Generic, data-driven market picker. The option list always comes from
 * `markets` (backed by `GET /api/v1/markets`) — no symbol is ever
 * hardcoded, so a new market becomes selectable the moment it exists in the
 * database, with no code change (Objective #2).
 *
 * Standalone/reusable: pass any `markets` array and a `value`/`onChange`
 * pair. Not used directly on the History page today, which already has an
 * equivalent selector in `HistoryForm` — see FRONTEND.md "Chart module" for
 * why the two aren't merged.
 */
export function MarketSelector({
  markets,
  value,
  onChange,
  loading = false,
  size = 'small',
}: MarketSelectorProps) {
  const selected = markets.find((market) => market.symbol === value) ?? null;
  return (
    <Autocomplete
      value={selected}
      onChange={(_, option) => onChange(option?.symbol ?? '')}
      options={markets}
      getOptionLabel={(option) => option.symbol}
      isOptionEqualToValue={(option, candidate) => option.symbol === candidate.symbol}
      loading={loading}
      size={size}
      disableClearable={Boolean(value)}
      sx={{ minWidth: 200, maxWidth: 280 }}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Market"
          placeholder="e.g. ETHUSD"
          inputProps={{ ...params.inputProps, 'aria-label': 'Select a market for the chart' }}
        />
      )}
    />
  );
}
