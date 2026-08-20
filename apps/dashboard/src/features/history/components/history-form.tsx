'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';
import type { Market } from '@/types/api/market';
import { HISTORY_LIMIT_OPTIONS, useTimeframes } from '../hooks/use-history-data';
import { RANGE_PRESET_LABELS, type RangePreset } from '../lib/resolve-range';

export { HISTORY_LIMIT_OPTIONS };

const datePattern = /^\d{4}-\d{2}-\d{2}$/;

export const HistoryFormSchema = z
  .object({
    market: z.string().min(1, 'Select a market'),
    timeframe: z.string().min(1, 'Select a timeframe'),
    range: z.enum(['all', 'today', 'yesterday', '24h', '7d', '30d', 'custom']),
    start: z.string().regex(datePattern, 'Use YYYY-MM-DD').optional().or(z.literal('')),
    end: z.string().regex(datePattern, 'Use YYYY-MM-DD').optional().or(z.literal('')),
    limit: z.number().int().min(1).max(1000),
  })
  .refine((values) => !values.start || !values.end || values.end >= values.start, {
    message: 'End date must be on or after the start date',
    path: ['end'],
  });

export type HistoryFormValues = z.infer<typeof HistoryFormSchema>;

export interface HistoryFormProps {
  markets: Market[] | undefined;
  defaultMarket: string;
  defaultRange: RangePreset;
  onSubmitted: (values: HistoryFormValues) => void;
}

export function HistoryForm({
  markets,
  defaultMarket,
  defaultRange,
  onSubmitted,
}: HistoryFormProps) {
  const {
    control,
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<HistoryFormValues>({
    resolver: zodResolver(HistoryFormSchema),
    defaultValues: {
      market: defaultMarket,
      timeframe: '',
      range: defaultRange,
      start: '',
      end: '',
      limit: 100,
    },
  });

  const marketSymbol = watch('market');
  const range = watch('range');
  const customRange = range === 'custom';
  const timeframes = useTimeframes(marketSymbol || null);
  const timeframesList = timeframes.data?.timeframes ?? [];
  const loadingTimeframes = timeframes.isLoading && Boolean(marketSymbol);

  return (
    <Box
      component="form"
      role="search"
      aria-label="Query historical candles"
      onSubmit={handleSubmit(onSubmitted)}
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'flex-start' }}
    >
      <Controller
        name="market"
        control={control}
        render={({ field }) => (
          <Autocomplete
            value={markets?.find((market) => market.symbol === field.value) ?? null}
            onChange={(_, option) => field.onChange(option?.symbol ?? '')}
            options={markets ?? []}
            getOptionLabel={(option) => option.symbol}
            loading={timeframes.isLoading && Boolean(marketSymbol)}
            isOptionEqualToValue={(option, value) => option.symbol === value.symbol}
            size="small"
            sx={{ minWidth: 220, maxWidth: 320, flexGrow: 1 }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Market"
                placeholder="e.g. BTCUSD"
                error={Boolean(errors.market)}
                helperText={errors.market?.message}
                inputProps={{
                  ...params.inputProps,
                  'aria-label': 'Select a market',
                }}
              />
            )}
          />
        )}
      />
      <Controller
        name="timeframe"
        control={control}
        render={({ field }) => (
          <TextField
            select
            label="Timeframe"
            size="small"
            value={field.value}
            onChange={field.onChange}
            inputRef={field.ref}
            error={Boolean(errors.timeframe)}
            helperText={errors.timeframe?.message}
            slotProps={{ select: { 'aria-label': 'Select a timeframe' } }}
            disabled={!marketSymbol || loadingTimeframes}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="" disabled>
              {loadingTimeframes ? 'Loading…' : 'Select…'}
            </MenuItem>
            {timeframesList.map((timeframe) => (
              <MenuItem key={timeframe} value={timeframe}>
                {timeframe}
              </MenuItem>
            ))}
          </TextField>
        )}
      />
      <Controller
        name="range"
        control={control}
        render={({ field }) => (
          <TextField
            select
            label="Range"
            size="small"
            value={field.value}
            onChange={field.onChange}
            inputRef={field.ref}
            slotProps={{ select: { 'aria-label': 'Select a range' } }}
            sx={{ minWidth: 150 }}
          >
            {(Object.keys(RANGE_PRESET_LABELS) as RangePreset[]).map((preset) => (
              <MenuItem key={preset} value={preset}>
                {RANGE_PRESET_LABELS[preset]}
              </MenuItem>
            ))}
          </TextField>
        )}
      />
      <TextField
        label="Start"
        type="date"
        size="small"
        {...register('start')}
        disabled={!customRange}
        error={Boolean(errors.start)}
        helperText={errors.start?.message}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Start date' } }}
        sx={{ minWidth: 170 }}
      />
      <TextField
        label="End"
        type="date"
        size="small"
        {...register('end')}
        disabled={!customRange}
        error={Boolean(errors.end)}
        helperText={
          customRange ? (errors.end?.message ?? 'The end day is included in full') : undefined
        }
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'End date' } }}
        sx={{ minWidth: 170 }}
      />
      <Controller
        name="limit"
        control={control}
        render={({ field }) => (
          <TextField
            select
            label="Page size"
            size="small"
            value={field.value}
            onChange={(event) => field.onChange(Number(event.target.value))}
            inputRef={field.ref}
            slotProps={{ select: { 'aria-label': 'Rows per page' } }}
            sx={{ minWidth: 130 }}
          >
            {HISTORY_LIMIT_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {option} / page
              </MenuItem>
            ))}
          </TextField>
        )}
      />
      <Button type="submit" variant="contained" size="medium" sx={{ mt: 0.5 }}>
        Query
      </Button>
    </Box>
  );
}
