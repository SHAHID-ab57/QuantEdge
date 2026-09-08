'use client';

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';

export interface NewsFiltersValue {
  symbol: string;
  start: string;
  end: string;
}

export interface NewsFiltersProps {
  value: NewsFiltersValue;
  onChange: (value: NewsFiltersValue) => void;
}

/** Filter bar for `/news` — symbol and a published_at date range, reusing
 * the same TextField/date-input visual pattern `history-form.tsx` already
 * established, sized down: this page has no market/timeframe selection
 * or dependent fields, so a full react-hook-form + zod resolver would be
 * more machinery than the filter set actually needs. */
export function NewsFilters({ value, onChange }: NewsFiltersProps) {
  return (
    <Box
      role="search"
      aria-label="Filter news articles"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'flex-start' }}
    >
      <TextField
        label="Symbol"
        placeholder="e.g. ETHUSD"
        size="small"
        value={value.symbol}
        onChange={(event) => onChange({ ...value, symbol: event.target.value.toUpperCase() })}
        inputProps={{ 'aria-label': 'Filter by symbol' }}
        sx={{ minWidth: 160 }}
      />
      <TextField
        label="Start"
        type="date"
        size="small"
        value={value.start}
        onChange={(event) => onChange({ ...value, start: event.target.value })}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Start date' } }}
        sx={{ minWidth: 170 }}
      />
      <TextField
        label="End"
        type="date"
        size="small"
        value={value.end}
        onChange={(event) => onChange({ ...value, end: event.target.value })}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'End date' } }}
        sx={{ minWidth: 170 }}
      />
      {(value.symbol || value.start || value.end) && (
        <Button
          size="small"
          onClick={() => onChange({ symbol: '', start: '', end: '' })}
          sx={{ mt: 0.5 }}
        >
          Clear
        </Button>
      )}
    </Box>
  );
}
