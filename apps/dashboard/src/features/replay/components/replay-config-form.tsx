'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { memo } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { useTimeframes } from '@/features/history/hooks/use-history-data';

const isoLocalPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

export const ReplayConfigFormSchema = z
  .object({
    market: z.string().min(1, 'Select a market'),
    timeframe: z.string().min(1, 'Select a timeframe'),
    start: z.string().regex(isoLocalPattern, 'Choose a start date and time'),
    end: z.string().regex(isoLocalPattern, 'Choose an end date and time'),
  })
  .refine((values) => new Date(values.end) > new Date(values.start), {
    message: 'End must be after the start',
    path: ['end'],
  })
  .refine((values) => new Date(values.end) <= new Date(), {
    message: 'End cannot be in the future',
    path: ['end'],
  });

export type ReplayConfigFormValues = z.infer<typeof ReplayConfigFormSchema>;

export interface ReplayConfigFormProps {
  onSubmitted: (values: ReplayConfigFormValues) => void;
  defaultValues?: Partial<ReplayConfigFormValues>;
  disabled?: boolean;
}

/**
 * Session configuration: market, timeframe, start, and end — the four
 * inputs a replay session needs before any data is fetched. Validated with
 * the same react-hook-form + Zod pattern as `HistoryForm`, adapted to
 * datetime-local inputs (rather than whole calendar days) since a replay
 * session is often scoped to a few hours, not whole days.
 *
 * Deliberately does not try to pre-validate "will this exceed
 * `MAX_REPLAY_CANDLES`" here — that depends on the timeframe's actual
 * candle duration, which this form has no reliable way to know client-side
 * for every symbol. That check happens after the data loads (see
 * `useReplayCandles`/`ReplayStatus`), where the real candle count is known.
 *
 * `React.memo`-wrapped: its props (`onSubmitted`, `defaultValues`) are
 * stable references from `ReplayPage`, and `disabled` only flips between
 * loads — but `ReplayPage` itself re-renders on every playback tick (the
 * engine's `currentIndex` lives there), and without this the form would
 * re-render (and, per its own `useForm`/`useMarkets`/`useTimeframes` calls,
 * redo real work) in lockstep with every candle instead of only when its
 * own props actually change. Verified directly in
 * `replay-page.render.test.tsx` by spying on `useTimeframes` (called
 * unconditionally in this component's render body) and asserting the call
 * count does not grow across several playback ticks — removing this
 * `memo` wrapper makes that test fail immediately.
 */
function ReplayConfigFormInner({
  onSubmitted,
  defaultValues,
  disabled = false,
}: ReplayConfigFormProps) {
  const markets = useMarkets();
  const {
    control,
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ReplayConfigFormValues>({
    resolver: zodResolver(ReplayConfigFormSchema),
    defaultValues: {
      market: '',
      timeframe: '',
      start: '',
      end: '',
      ...defaultValues,
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
      aria-label="Configure a replay session"
      onSubmit={handleSubmit(onSubmitted)}
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'flex-start' }}
    >
      <Controller
        name="market"
        control={control}
        render={({ field }) => (
          <Autocomplete
            value={markets.data?.markets.find((market) => market.symbol === field.value) ?? null}
            onChange={(_, option) => field.onChange(option?.symbol ?? '')}
            options={markets.data?.markets ?? []}
            getOptionLabel={(option) => option.symbol}
            loading={markets.isLoading}
            isOptionEqualToValue={(option, value) => option.symbol === value.symbol}
            size="small"
            disabled={disabled}
            sx={{ minWidth: 200, maxWidth: 280 }}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Market"
                placeholder="e.g. ETHUSD"
                error={Boolean(errors.market)}
                helperText={errors.market?.message}
                inputProps={{ ...params.inputProps, 'aria-label': 'Select a market to replay' }}
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
            disabled={disabled || !marketSymbol || loadingTimeframes}
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
      <TextField
        label="Start"
        type="datetime-local"
        size="small"
        disabled={disabled}
        {...register('start')}
        error={Boolean(errors.start)}
        helperText={errors.start?.message}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Replay start' } }}
        sx={{ minWidth: 210 }}
      />
      <TextField
        label="End"
        type="datetime-local"
        size="small"
        disabled={disabled}
        {...register('end')}
        error={Boolean(errors.end)}
        helperText={errors.end?.message}
        slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'aria-label': 'Replay end' } }}
        sx={{ minWidth: 210 }}
      />
      <Button type="submit" variant="contained" size="medium" disabled={disabled} sx={{ mt: 0.5 }}>
        Load Session
      </Button>
    </Box>
  );
}

export const ReplayConfigForm = memo(ReplayConfigFormInner);
