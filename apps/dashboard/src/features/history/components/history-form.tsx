'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Autocomplete from '@mui/material/Autocomplete';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';
import type { Market } from '@/types/api/market';
import { useTimeframes } from '../hooks/use-history-data';

export const HISTORY_LIMIT_OPTIONS = [100, 250, 500, 1000];

const datePattern = /^\d{4}-\d{2}-\d{2}$/;

export const HistoryFormSchema = z
  .object({
    market: z.string().min(1, 'Select a market'),
    timeframe: z.string().min(1, 'Select a timeframe'),
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
  onSubmitted: (values: HistoryFormValues) => void;
}

export function HistoryForm({ markets, defaultMarket, onSubmitted }: HistoryFormProps) {
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
      start: '',
      end: '',
      limit: 100,
    },
  });

  const marketSymbol = watch('market');
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
      <TextField
        select
        label="Timeframe"
        size="small"
        {...register('timeframe')}
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
      <TextField
        label="Start"
        type="date"
        size="small"
        {...register('start')}
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
        error={Boolean(errors.end)}
        helperText={errors.end?.message ?? 'The end day is included in full'}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'End date' } }}
        sx={{ minWidth: 170 }}
      />
      <TextField
        select
        label="Page size"
        size="small"
        {...register('limit', { valueAsNumber: true })}
        slotProps={{ select: { 'aria-label': 'Rows per page' } }}
        sx={{ minWidth: 130 }}
      >
        {HISTORY_LIMIT_OPTIONS.map((option) => (
          <MenuItem key={option} value={option}>
            {option} / page
          </MenuItem>
        ))}
      </TextField>
      <Button type="submit" variant="contained" size="medium" sx={{ mt: 0.5 }}>
        Query
      </Button>
    </Box>
  );
}
