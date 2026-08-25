'use client';

import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { useState } from 'react';
import { useTimeframes } from '@/features/history/hooks/use-history-data';
import { RANGE_PRESET_LABELS, type RangePreset } from '@/features/history/lib/resolve-range';
import type { Market } from '@/types/api/market';

/**
 * Market, timeframe, and date-range selection for a dataset build.
 *
 * Reuses the History feature module's `useTimeframes` hook and its
 * `RangePreset` vocabulary rather than declaring either again: "which
 * timeframes does this market have candles for" and "what does 'Last 7
 * Days' mean" are answered once for the whole platform, and two answers
 * would eventually disagree.
 *
 * Deliberately *not* react-hook-form + Zod like `HistoryForm`. That form
 * validates six interdependent fields including a cross-field date-order
 * rule; this one has three fields whose only rule is "all present", so a
 * schema and resolver would be more machinery than the problem has. The
 * submit button is simply disabled until the form can produce a valid
 * request, which is both simpler and a clearer affordance.
 */

export interface DatasetFormValues {
  market: string;
  timeframe: string;
  range: RangePreset;
  start: string;
  end: string;
  limit: number;
}

export const DATASET_ROW_OPTIONS = [100, 250, 500, 1000] as const;

export interface DatasetFormProps {
  markets: Market[] | undefined;
  values: DatasetFormValues;
  onChange: (values: DatasetFormValues) => void;
  onSubmit: () => void;
  /** True while a build is in flight, so the action reads as busy rather than broken. */
  busy?: boolean;
  /** Disables submit when no feature is selected, with the reason shown by the caller. */
  canSubmit?: boolean;
}

export function DatasetForm({
  markets,
  values,
  onChange,
  onSubmit,
  busy = false,
  canSubmit = true,
}: DatasetFormProps) {
  const [touched, setTouched] = useState(false);
  const timeframes = useTimeframes(values.market || null);
  const timeframeList = timeframes.data?.timeframes ?? [];
  const loadingTimeframes = timeframes.isLoading && Boolean(values.market);
  const customRange = values.range === 'custom';

  const set = <K extends keyof DatasetFormValues>(key: K, value: DatasetFormValues[K]) => {
    // Changing the market invalidates the timeframe: the new market may not
    // store candles for it, and silently keeping a stale one would send a
    // request guaranteed to 404.
    const next =
      key === 'market'
        ? { ...values, market: value as string, timeframe: '' }
        : { ...values, [key]: value };
    onChange(next);
  };

  const datesValid = !customRange || !values.start || !values.end || values.end >= values.start;
  const ready = Boolean(values.market) && Boolean(values.timeframe) && datesValid && canSubmit;

  return (
    <Box
      component="form"
      role="search"
      aria-label="Configure feature dataset"
      onSubmit={(event) => {
        event.preventDefault();
        setTouched(true);
        if (ready) {
          onSubmit();
        }
      }}
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'flex-start' }}
    >
      <Autocomplete
        value={markets?.find((market) => market.symbol === values.market) ?? null}
        onChange={(_, option) => set('market', option?.symbol ?? '')}
        options={markets ?? []}
        getOptionLabel={(option) => option.symbol}
        isOptionEqualToValue={(option, value) => option.symbol === value.symbol}
        size="small"
        sx={{ minWidth: 220, maxWidth: 320, flexGrow: 1 }}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Market"
            placeholder="e.g. ETHUSD"
            error={touched && !values.market}
            helperText={touched && !values.market ? 'Select a market' : undefined}
            slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Select a market' } }}
          />
        )}
      />

      <TextField
        select
        label="Timeframe"
        size="small"
        value={values.timeframe}
        onChange={(event) => set('timeframe', event.target.value)}
        disabled={!values.market || loadingTimeframes}
        error={touched && Boolean(values.market) && !values.timeframe}
        helperText={
          touched && Boolean(values.market) && !values.timeframe ? 'Select a timeframe' : undefined
        }
        slotProps={{ select: { 'aria-label': 'Select a timeframe' } }}
        sx={{ minWidth: 140 }}
      >
        <MenuItem value="" disabled>
          {loadingTimeframes ? 'Loading…' : 'Select…'}
        </MenuItem>
        {timeframeList.map((timeframe) => (
          <MenuItem key={timeframe} value={timeframe}>
            {timeframe}
          </MenuItem>
        ))}
      </TextField>

      <TextField
        select
        label="Range"
        size="small"
        value={values.range}
        onChange={(event) => set('range', event.target.value as RangePreset)}
        slotProps={{ select: { 'aria-label': 'Select a range' } }}
        sx={{ minWidth: 150 }}
      >
        {(Object.keys(RANGE_PRESET_LABELS) as RangePreset[]).map((preset) => (
          <MenuItem key={preset} value={preset}>
            {RANGE_PRESET_LABELS[preset]}
          </MenuItem>
        ))}
      </TextField>

      <TextField
        label="Start"
        type="date"
        size="small"
        value={values.start}
        onChange={(event) => set('start', event.target.value)}
        disabled={!customRange}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Start date' } }}
        sx={{ minWidth: 170 }}
      />
      <TextField
        label="End"
        type="date"
        size="small"
        value={values.end}
        onChange={(event) => set('end', event.target.value)}
        disabled={!customRange}
        error={!datesValid}
        helperText={!datesValid ? 'End date must be on or after the start date' : undefined}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'End date' } }}
        sx={{ minWidth: 170 }}
      />

      <TextField
        select
        label="Max rows"
        size="small"
        value={values.limit}
        onChange={(event) => set('limit', Number(event.target.value))}
        slotProps={{ select: { 'aria-label': 'Maximum dataset rows' } }}
        sx={{ minWidth: 140 }}
      >
        {DATASET_ROW_OPTIONS.map((option) => (
          <MenuItem key={option} value={option}>
            {option} rows
          </MenuItem>
        ))}
      </TextField>

      <Button type="submit" variant="contained" disabled={!ready || busy} sx={{ mt: 0.5 }}>
        {busy ? 'Building…' : 'Build Dataset'}
      </Button>
    </Box>
  );
}
