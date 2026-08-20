'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useCallback, useState } from 'react';
import { ApiError } from '@/lib/api/errors';
import { CandlesTable } from './components/candles-table';
import { ExportButtons } from './components/export-buttons';
import { HistoryForm, type HistoryFormValues } from './components/history-form';
import { PerformanceCard } from './components/performance-card';
import { StatsCard } from './components/stats-card';
import {
  type HistoryQuery,
  useCandles,
  useCandleStats,
  useMarkets,
} from './hooks/use-history-data';

function convertToQuery(values: HistoryFormValues): HistoryQuery {
  const start = values.start ? `${values.start}T00:00:00Z` : null;
  const end = values.end
    ? new Date(new Date(`${values.end}T00:00:00Z`).getTime() + 86_400_000)
        .toISOString()
        .replace(/\.\d{3}Z$/, 'Z')
    : null;
  return {
    symbol: values.market,
    timeframe: values.timeframe,
    start,
    end,
    limit: values.limit,
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
  const [query, setQuery] = useState<HistoryQuery | null>(null);
  const [page, setPage] = useState(1);

  const candles = useCandles(query, page);
  const stats = useCandleStats(query);

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

  const handleRetry = useCallback(() => {
    markets.refetch();
    if (query) {
      setQuery({ ...query });
    }
  }, [markets, query]);

  const total = candles.data?.page.pagination.total ?? 0;
  const statsEmpty = stats.error instanceof ApiError && stats.error.status === 404;
  const filtersLoading = Boolean(query) && candles.isLoading && !candles.data;

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
            <CandlesTable
              data={candles.data}
              isLoading={candles.isLoading}
              page={page}
              limit={query.limit}
              onPageChange={handlePageChange}
              onLimitChange={handleLimitChange}
            />
            {filtersLoading ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Loading page {page}…
              </Typography>
            ) : null}
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <Stack spacing={2}>
              <StatsCard
                stats={stats.data}
                isLoading={stats.isLoading}
                isEmpty={statsEmpty || total === 0}
              />
              <PerformanceCard
                query={query}
                page={page}
                latencyMs={candles.data?.latencyMs ?? null}
                returned={candles.data?.page.pagination.returned ?? 0}
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
