'use client';

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Typography from '@mui/material/Typography';
import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChartContainer } from '@/components/chart';
import {
  IndicatorLegend,
  IndicatorPanel,
  useChartOverlays,
  useOverlayStore,
} from '@/features/indicator-overlays';
import { useIndicatorCatalog } from '@/features/indicators/hooks/use-indicator-data';
import { resolveRange } from './lib/resolve-range';
import { CandlesTable } from './components/candles-table';
import { ExportButtons } from './components/export-buttons';
import { HistoryForm, type HistoryFormValues } from './components/history-form';
import { PerformanceCard } from './components/performance-card';
import { QualityCard } from './components/quality-card';
import { StatsCard } from './components/stats-card';
import {
  type CandleSortColumn,
  type CandleSortDirection,
  type HistoryQuery,
  useCandles,
  useMarkets,
} from './hooks/use-history-data';
import { queryFromSearchParams, useHistoryUrlState } from './hooks/use-history-url-state';

const DAY_MS = 86_400_000;

function convertToQuery(values: HistoryFormValues): HistoryQuery {
  const resolved = resolveRange(values.range);
  const start =
    values.range === 'custom' && values.start ? `${values.start}T00:00:00Z` : resolved.start;
  const end =
    values.range === 'custom' && values.end
      ? new Date(new Date(`${values.end}T00:00:00Z`).getTime() + DAY_MS)
          .toISOString()
          .replace(/\.\d{3}Z$/, 'Z')
      : resolved.end;
  return {
    symbol: values.market,
    timeframe: values.timeframe,
    start,
    end,
    limit: values.limit,
    sort: 'open_time',
    dir: 'asc',
  };
}

function HistorySkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading history data">
      <Skeleton variant="rounded" height={56} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Skeleton variant="rounded" height={420} />
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Skeleton variant="rounded" height={220} />
        </Grid>
      </Grid>
    </Stack>
  );
}

export function HistoryPage() {
  const markets = useMarkets();
  const searchParams = useSearchParams();
  const { apply } = useHistoryUrlState();

  const initial = useMemo(
    () => queryFromSearchParams(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );
  const [query, setQuery] = useState<HistoryQuery | null>(initial?.query ?? null);
  const [page, setPage] = useState(initial?.page ?? 1);
  const [view, setView] = useState<'chart' | 'table'>('table');

  useEffect(() => {
    if (query) {
      apply(query, page);
    }
  }, [apply, page, query]);

  const candles = useCandles(query, page);
  const catalog = useIndicatorCatalog();
  const storeOverlays = useOverlayStore((state) => state.overlays);
  const chartOverlays = useChartOverlays({
    symbol: query?.symbol ?? null,
    timeframe: query?.timeframe ?? null,
    start: query?.start ?? undefined,
    end: query?.end ?? undefined,
  });

  const handleSubmitted = useCallback((values: HistoryFormValues) => {
    setQuery(convertToQuery(values));
    setPage(1);
  }, []);

  const handlePageChange = useCallback((nextPage: number) => {
    setPage(nextPage);
  }, []);

  const handleLimitChange = useCallback(
    (limit: number) => {
      if (query) {
        setQuery({ ...query, limit });
        setPage(1);
      }
    },
    [query],
  );

  const handleSortChange = useCallback(
    (sort: CandleSortColumn, dir: CandleSortDirection) => {
      if (query) {
        setQuery({ ...query, sort, dir });
        setPage(1);
      }
    },
    [query],
  );

  const handleRetry = useCallback(() => {
    markets.refetch();
    if (query) {
      setQuery({ ...query });
    }
  }, [markets, query]);

  const pageData = candles.data;
  const total = pageData?.pagination.total ?? 0;
  const filtersLoading = Boolean(query) && candles.isLoading && !candles.data;
  const queryEmpty = query !== null && total === 0;

  if (markets.isLoading) {
    return <HistorySkeleton />;
  }

  if (markets.isError) {
    return (
      <Alert severity="error" role="alert" action={<Button onClick={handleRetry}>Retry</Button>}>
        Failed to load markets: {markets.error.message}
      </Alert>
    );
  }

  const marketList = markets.data?.markets ?? [];

  return (
    <Stack spacing={2}>
      <HistoryForm
        markets={marketList}
        defaultMarket={query?.symbol ?? ''}
        defaultRange={query?.start && query?.end ? 'custom' : 'all'}
        onSubmitted={handleSubmitted}
      />

      {!query ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1" color="text.secondary">
            Select a market and timeframe, then run a query to explore historical candles.
          </Typography>
        </Paper>
      ) : null}

      {query && candles.isError ? (
        <Alert severity="error" role="alert" action={<Button onClick={handleRetry}>Retry</Button>}>
          Failed to load candles: {candles.error.message}
        </Alert>
      ) : null}

      {query && !candles.isError ? (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <Tabs
              value={view}
              onChange={(_, next: 'chart' | 'table') => setView(next)}
              sx={{ mb: 1, minHeight: 36 }}
            >
              <Tab label="Chart" value="chart" sx={{ minHeight: 36, py: 0 }} />
              <Tab label="Table" value="table" sx={{ minHeight: 36, py: 0 }} />
            </Tabs>
            {view === 'chart' ? (
              <>
                <ChartContainer
                  symbol={query.symbol}
                  timeframe={query.timeframe}
                  start={query.start}
                  end={query.end}
                  overlays={chartOverlays.chartOverlays}
                />
                <Box sx={{ mt: 1 }}>
                  <IndicatorLegend
                    overlays={storeOverlays}
                    overlaySeries={chartOverlays.overlaySeries}
                    isLoading={chartOverlays.isLoading}
                    symbol={query.symbol}
                    timeframe={query.timeframe}
                  />
                </Box>
              </>
            ) : null}
            {view === 'table' ? (
              <>
                <CandlesTable
                  data={pageData}
                  isLoading={candles.isLoading}
                  page={page}
                  limit={query.limit}
                  sort={query.sort}
                  dir={query.dir}
                  onPageChange={handlePageChange}
                  onLimitChange={handleLimitChange}
                  onSortChange={handleSortChange}
                />
                {filtersLoading ? (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', mt: 1 }}
                  >
                    Loading page {page}…
                  </Typography>
                ) : null}
              </>
            ) : null}
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
                <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 700, mb: 1.5 }}>
                  Indicators
                </Typography>
                <IndicatorPanel
                  indicators={catalog.data?.indicators ?? []}
                  loading={catalog.isLoading}
                />
              </Paper>
              <StatsCard
                statistics={pageData?.statistics}
                isLoading={candles.isLoading && !candles.data}
                isEmpty={queryEmpty}
              />
              <QualityCard
                quality={pageData?.quality}
                isLoading={candles.isLoading && !candles.data}
                isEmpty={queryEmpty}
              />
              <PerformanceCard
                query={query}
                page={page}
                meta={pageData?.meta}
                returned={pageData?.pagination.returned ?? 0}
                total={total}
              />
              <ExportButtons query={query} disabled={candles.isLoading || total === 0} />
            </Stack>
          </Grid>
        </Grid>
      ) : null}
    </Stack>
  );
}
