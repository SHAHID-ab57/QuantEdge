'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { MarketSelector } from '@/components/chart/market-selector';
import { Section } from '@/components/section';
import { useTimeframes } from '@/features/history/hooks/use-history-data';
import { useMarkets } from '@/features/markets/hooks/use-markets-data';
import { ExportMenu } from './components/export-menu';
import { FieldInfo } from './components/field-info';
import { IndicatorInfoPanel } from './components/indicator-info-panel';
import { IndicatorMetadataCard } from './components/indicator-metadata-card';
import { IndicatorSelector } from './components/indicator-selector';
import { ParameterForm } from './components/parameter-form';
import { RecentCalculationsPanel } from './components/recent-calculations-panel';
import { ResultsPanel } from './components/results-panel';
import {
  useIndicatorCalculation,
  useIndicatorCatalog,
  type IndicatorRequest,
} from './hooks/use-indicator-data';
import { useCurrentPrice } from './hooks/use-current-price';
import { useRecentCalculations } from './hooks/use-recent-calculations';
import { extractCurrentPrice } from './lib/current-price';
import { getIndicatorKnowledge } from './lib/indicator-knowledge';
import {
  defaultValuesFor,
  toRequestParams,
  validateValues,
  type ParameterValues,
} from './lib/parameter-values';
import type { RecentCalculation } from './lib/recent-calculations';

interface RerunOverride {
  indicator: string;
  params: Record<string, string>;
}

/**
 * The indicator research page: pick a market, timeframe, and indicator,
 * fill in its parameters, and see the computed series alongside research
 * context (what it measures, how to read it), engine metadata, and
 * researcher export/rerun utilities.
 *
 * The parameter form is generated entirely from the backend's published
 * specs (see `ParameterForm`), so this page has no per-indicator
 * *functional* code at all — registering a new indicator on the backend
 * makes it appear here, correctly constrained, with no frontend change.
 * `lib/indicator-knowledge.ts` is a separate, purely additive enrichment
 * layer (research content, chart config, signal thresholds) that degrades
 * gracefully to an honest "not yet documented" for an indicator it has no
 * curated entry for — never a blank or broken page.
 *
 * No chart overlays onto the candlestick module: this page's chart (see
 * `IndicatorChart`) visualizes the computed series on their own, reusing
 * the same dependency-free SVG technique as the Trade Analytics
 * `Sparkline` rather than a second charting engine.
 */
export function IndicatorsPage() {
  const markets = useMarkets();
  const catalog = useIndicatorCatalog();
  const { entries: recentCalculations, record: recordCalculation } = useRecentCalculations();

  const [symbol, setSymbol] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('');
  const [indicatorName, setIndicatorName] = useState<string | null>(null);
  const [values, setValues] = useState<ParameterValues>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [request, setRequest] = useState<IndicatorRequest | null>(null);
  const [rerunOverride, setRerunOverride] = useState<RerunOverride | null>(null);

  const timeframes = useTimeframes(symbol);
  const timeframeOptions = useMemo(() => timeframes.data?.timeframes ?? [], [timeframes.data]);

  const indicators = useMemo(() => catalog.data?.indicators ?? [], [catalog.data]);
  const selected = useMemo(
    () => indicators.find((entry) => entry.name === indicatorName) ?? null,
    [indicators, indicatorName],
  );
  const knowledge = useMemo(() => (selected ? getIndicatorKnowledge(selected) : null), [selected]);

  // Reseed the form whenever the chosen indicator changes: the previous
  // indicator's values are meaningless for a different parameter set, and
  // carrying them over would silently send the wrong thing. A pending
  // rerun overrides the fresh defaults with the exact parameters that
  // configuration used, once the matching indicator becomes selected.
  useEffect(() => {
    if (!selected) {
      return;
    }
    if (rerunOverride && rerunOverride.indicator === selected.name) {
      setValues({ ...defaultValuesFor(selected.parameters), ...rerunOverride.params });
      setRerunOverride(null);
    } else {
      setValues(defaultValuesFor(selected.parameters));
    }
    setErrors({});
  }, [selected, rerunOverride]);

  // A stored timeframe that exists for one market may not exist for the
  // next; clear rather than submit a combination with no candles.
  useEffect(() => {
    if (timeframe && timeframeOptions.length > 0 && !timeframeOptions.includes(timeframe)) {
      setTimeframe('');
    }
  }, [timeframe, timeframeOptions]);

  const handleParameterChange = useCallback((name: string, value: string) => {
    setValues((previous) => ({ ...previous, [name]: value }));
  }, []);

  const handleCalculate = useCallback(() => {
    if (!symbol || !timeframe || !selected) {
      return;
    }
    const found = validateValues(selected.parameters, values);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    setRequest({
      symbol,
      indicator: selected.name,
      timeframe,
      params: toRequestParams(values),
    });
  }, [symbol, timeframe, selected, values]);

  const calculation = useIndicatorCalculation(request);
  const canCalculate = Boolean(symbol && timeframe && selected);

  // One-click rerun: fires the calculation immediately from the entry's
  // own resolved parameters (skipping client validation — a previously
  // successful configuration is already known-good) while the form's
  // visible fields catch up via the reseed effect above.
  const handleRerun = useCallback((entry: RecentCalculation) => {
    setSymbol(entry.symbol);
    setTimeframe(entry.timeframe);
    setIndicatorName(entry.indicator);
    setRerunOverride({ indicator: entry.indicator, params: entry.params });
    setRequest({
      symbol: entry.symbol,
      indicator: entry.indicator,
      timeframe: entry.timeframe,
      params: entry.params,
    });
  }, []);

  // Records every successful calculation using the response's own echoed
  // symbol/indicator/timeframe/parameters — the fully-resolved values
  // (defaults included), not just what the researcher happened to type —
  // so a rerun reproduces exactly what ran.
  useEffect(() => {
    const data = calculation.data;
    if (!data) {
      return;
    }
    recordCalculation({
      symbol: data.symbol,
      indicator: data.indicator.name,
      indicatorLabel: data.indicator.label,
      timeframe: data.timeframe,
      params: Object.fromEntries(
        Object.entries(data.parameters).map(([key, value]) => [key, String(value)]),
      ),
      timestamp: Date.now(),
    });
  }, [calculation.data, recordCalculation]);

  const resultKnowledge = useMemo(
    () => (calculation.data ? getIndicatorKnowledge(calculation.data.indicator) : undefined),
    [calculation.data],
  );
  const metadataResult =
    selected && calculation.data?.indicator.name === selected.name ? calculation.data : undefined;

  // Current Price / Distance from Current Price need the market's raw
  // price, which the indicator calculation response never carries (it
  // returns indicator values, not candles) — reused here from the
  // existing latest-candle endpoint instead of growing that response.
  const latestCandle = useCurrentPrice(
    calculation.data?.symbol ?? null,
    calculation.data?.timeframe ?? '',
  );
  const currentPrice = useMemo(() => {
    if (!latestCandle.data || !calculation.data) {
      return undefined;
    }
    return extractCurrentPrice(latestCandle.data.candle, calculation.data.parameters.source);
  }, [latestCandle.data, calculation.data]);

  if (catalog.isLoading) {
    return (
      <Stack spacing={2} role="status" aria-label="Loading indicators">
        <Skeleton variant="rounded" height={140} />
        <Skeleton variant="rounded" height={320} />
      </Stack>
    );
  }

  if (catalog.isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button size="small" onClick={() => catalog.refetch()}>
            Retry
          </Button>
        }
      >
        Failed to load the indicator catalogue:{' '}
        {catalog.error?.message ?? 'the backend is unavailable.'}
      </Alert>
    );
  }

  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, lg: 8 }} sx={{ minWidth: 0 }}>
        <Stack spacing={2}>
          <Section title="Configuration" subtitle="Market, timeframe, and indicator to calculate">
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="flex-start">
              <Stack direction="row" spacing={0.25} alignItems="flex-start">
                <MarketSelector
                  markets={markets.data?.markets ?? []}
                  value={symbol}
                  onChange={setSymbol}
                  loading={markets.isLoading}
                />
                <FieldInfo field="market" label="Market" />
              </Stack>

              <Stack direction="row" spacing={0.25} alignItems="flex-start">
                <TextField
                  select
                  label="Timeframe"
                  size="small"
                  value={timeframe}
                  onChange={(event) => setTimeframe(event.target.value)}
                  disabled={!symbol || timeframes.isLoading}
                  helperText={
                    symbol && !timeframes.isLoading && timeframeOptions.length === 0
                      ? 'No stored candles for this market'
                      : undefined
                  }
                  sx={{ minWidth: 160 }}
                >
                  <MenuItem value="" disabled>
                    {timeframes.isLoading ? 'Loading…' : 'Select…'}
                  </MenuItem>
                  {timeframeOptions.map((option) => (
                    <MenuItem key={option} value={option}>
                      {option}
                    </MenuItem>
                  ))}
                </TextField>
                <FieldInfo field="timeframe" label="Timeframe" />
              </Stack>

              <Stack direction="row" spacing={0.25} alignItems="flex-start">
                <IndicatorSelector
                  indicators={indicators}
                  value={indicatorName}
                  onChange={setIndicatorName}
                  loading={catalog.isLoading}
                />
                <FieldInfo field="indicator" label="Indicator" />
              </Stack>
            </Stack>
          </Section>

          {selected && knowledge ? (
            <IndicatorInfoPanel key={selected.name} indicator={selected} />
          ) : null}

          <Section
            title="Parameters"
            subtitle="Generated from the indicator's published specification"
          >
            <Stack spacing={2} alignItems="flex-start">
              {selected ? (
                <ParameterForm
                  specs={selected.parameters}
                  values={values}
                  errors={errors}
                  onChange={handleParameterChange}
                  parameterKnowledge={knowledge?.parameters}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Select an indicator to configure its parameters.
                </Typography>
              )}
              <Button
                variant="contained"
                onClick={handleCalculate}
                disabled={!canCalculate || calculation.isFetching}
              >
                {calculation.isFetching ? 'Calculating…' : 'Calculate'}
              </Button>
            </Stack>
          </Section>

          <Section
            title="Results"
            subtitle="Values align with candle open times; nulls are warmup"
            action={
              calculation.data ? (
                <ExportMenu result={calculation.data} knowledge={resultKnowledge} />
              ) : undefined
            }
          >
            <ResultsPanel
              requested={request !== null}
              isPending={calculation.isPending}
              isError={calculation.isError}
              error={calculation.error}
              result={calculation.data}
              knowledge={resultKnowledge}
              currentPrice={currentPrice}
              onRetry={() => calculation.refetch()}
            />
          </Section>
        </Stack>
      </Grid>

      <Grid size={{ xs: 12, lg: 4 }} sx={{ minWidth: 0 }}>
        <Stack spacing={2}>
          {selected ? <IndicatorMetadataCard indicator={selected} result={metadataResult} /> : null}
          <RecentCalculationsPanel entries={recentCalculations} onRerun={handleRerun} />
        </Stack>
      </Grid>
    </Grid>
  );
}
