'use client';

import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState, type ReactNode } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
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

/**
 * One explanation per configurable field — Purpose / Expected values /
 * Validation rules / Example — rendered via the existing `InfoTooltip`
 * component. Placed as a sibling of each field (`FieldTooltip`, below)
 * rather than inside the MUI `label` prop: nesting an interactive icon
 * button inside a form control's `<label>` element is a known a11y trap
 * (a screen reader can double-announce or mis-associate it), so the
 * tooltip sits beside the field instead, leaving every field's own
 * `label`/`aria-label`/`helperText` — and therefore every existing test
 * that queries by them — completely unchanged.
 */
const FIELD_TOOLTIPS = {
  Market: [
    {
      heading: 'Purpose',
      body: 'Which exchange-listed symbol to build and validate a dataset for.',
    },
    {
      heading: 'Expected values',
      body: 'Any market symbol this platform tracks (e.g. ETHUSD, BTCUSD) — see the Markets page for the full list.',
    },
    {
      heading: 'Validation rules',
      body: 'Required. Must be a symbol this platform has stored candles for, or the request 404s.',
    },
    { heading: 'Example', body: 'ETHUSD' },
  ],
  Timeframe: [
    { heading: 'Purpose', body: 'The candle resolution (bucket size) to build the dataset from.' },
    {
      heading: 'Expected values',
      body: 'A resolution the chosen market has stored candles for, e.g. 1m, 5m, 1h, 4h, 1d.',
    },
    {
      heading: 'Validation rules',
      body: 'Required, and only selectable once a market is chosen — the list reflects that market’s own stored timeframes.',
    },
    { heading: 'Example', body: '1h' },
  ],
  Range: [
    { heading: 'Purpose', body: 'How far back the dataset should reach.' },
    {
      heading: 'Expected values',
      body: 'A preset (All History, Today, Last 7 Days, ...) or Custom Range with explicit start/end dates.',
    },
    {
      heading: 'Validation rules',
      body: 'Custom Range requires both a start and an end date, with the end on or after the start.',
    },
    { heading: 'Example', body: 'Last 30 Days' },
  ],
  Start: [
    { heading: 'Purpose', body: 'The first day included in a Custom Range dataset (inclusive).' },
    { heading: 'Expected values', body: 'A calendar date.' },
    { heading: 'Validation rules', body: 'Only editable when Range is set to Custom Range.' },
    { heading: 'Example', body: '2026-01-01' },
  ],
  End: [
    { heading: 'Purpose', body: 'The last day included in a Custom Range dataset (inclusive).' },
    { heading: 'Expected values', body: 'A calendar date on or after Start.' },
    {
      heading: 'Validation rules',
      body: 'Only editable when Range is set to Custom Range; must be on or after the start date.',
    },
    { heading: 'Example', body: '2026-01-31' },
  ],
  'Max rows': [
    {
      heading: 'Purpose',
      body: 'Caps how many rows the built dataset returns — not how many candles are read; extra candles needed for warmup are read on top of this.',
    },
    { heading: 'Expected values', body: 'One of the offered row counts.' },
    {
      heading: 'Validation rules',
      body: 'Must be a positive integer within the server’s configured maximum.',
    },
    { heading: 'Example', body: '500 rows' },
  ],
};

/** A field plus its explanatory tooltip, kept outside the field's own `<label>` — see `FIELD_TOOLTIPS`. */
function FieldTooltip({
  name,
  children,
}: {
  name: keyof typeof FIELD_TOOLTIPS;
  children: ReactNode;
}) {
  return (
    <Stack direction="row" spacing={0.25} alignItems="flex-start" sx={{ pt: 1 }}>
      {children}
      <InfoTooltip label={name} sections={FIELD_TOOLTIPS[name]} />
    </Stack>
  );
}

export interface DatasetFormProps {
  markets: Market[] | undefined;
  values: DatasetFormValues;
  onChange: (values: DatasetFormValues) => void;
  onSubmit: () => void;
  /** True while a build is in flight, so the action reads as busy rather than broken. */
  busy?: boolean;
  /** Disables submit when no feature is selected, with the reason shown by the caller. */
  canSubmit?: boolean;
  /** Submit button text while idle — a caller building something other than a preview
   * dataset (e.g. the Dataset Validation page's "Run Validation") can relabel the same
   * action rather than this module growing a second, near-identical form. */
  submitLabel?: string;
  /** Submit button text while `busy` is true. */
  busyLabel?: string;
}

export function DatasetForm({
  markets,
  values,
  onChange,
  onSubmit,
  busy = false,
  canSubmit = true,
  submitLabel = 'Build Dataset',
  busyLabel = 'Building…',
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
      <FieldTooltip name="Market">
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
      </FieldTooltip>

      <FieldTooltip name="Timeframe">
        <TextField
          select
          label="Timeframe"
          size="small"
          value={values.timeframe}
          onChange={(event) => set('timeframe', event.target.value)}
          disabled={!values.market || loadingTimeframes}
          error={touched && Boolean(values.market) && !values.timeframe}
          helperText={
            touched && Boolean(values.market) && !values.timeframe
              ? 'Select a timeframe'
              : undefined
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
      </FieldTooltip>

      <FieldTooltip name="Range">
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
      </FieldTooltip>

      <FieldTooltip name="Start">
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
      </FieldTooltip>
      <FieldTooltip name="End">
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
      </FieldTooltip>

      <FieldTooltip name="Max rows">
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
      </FieldTooltip>

      <Button type="submit" variant="contained" disabled={!ready || busy} sx={{ mt: 0.5 }}>
        {busy ? busyLabel : submitLabel}
      </Button>
    </Box>
  );
}
