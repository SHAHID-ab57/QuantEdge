'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMemo, useState } from 'react';
import type { Market } from '@/types/api/market';
import { DetailPanel } from './components/detail-panel';
import { MarketsTable } from './components/markets-table';
import { MarketsToolbar } from './components/toolbar';
import { useMarketUrlState } from './hooks/use-market-url-state';
import { useMarkets } from './hooks/use-markets-data';

function MarketsSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading markets">
      <Skeleton variant="rounded" height={56} />
      <Skeleton variant="rounded" height={420} />
    </Stack>
  );
}

function sortMarkets(markets: Market[], sort: string, dir: 'asc' | 'desc'): Market[] {
  const sorted = [...markets];
  sorted.sort((a, b) => {
    const left = a[sort as keyof Market];
    const right = b[sort as keyof Market];
    const comparison = String(left).localeCompare(String(right));
    return dir === 'asc' ? comparison : -comparison;
  });
  return sorted;
}

export function MarketsPage() {
  const markets = useMarkets();
  const { state, setSearch, setFilter, toggleSort, changePage, changeSize, clearFilters } =
    useMarketUrlState();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const exchanges = useMemo(
    () =>
      Array.from(new Set((markets.data?.markets ?? []).map((market) => market.exchange))).sort(),
    [markets.data],
  );

  const filtered = useMemo(() => {
    const q = state.q.trim().toLowerCase();
    return (markets.data?.markets ?? []).filter((market) => {
      if (q && !market.symbol.toLowerCase().includes(q)) {
        return false;
      }
      if (state.type && market.market_type !== state.type) {
        return false;
      }
      if (state.status === 'active' && !market.is_active) {
        return false;
      }
      if (state.status === 'inactive' && market.is_active) {
        return false;
      }
      if (state.exchange && market.exchange !== state.exchange) {
        return false;
      }
      return true;
    });
  }, [markets.data, state.q, state.type, state.status, state.exchange]);

  const sorted = useMemo(
    () => sortMarkets(filtered, state.sort, state.dir),
    [filtered, state.sort, state.dir],
  );

  const totalPages = Math.max(1, Math.ceil(sorted.length / state.size));
  const effectivePage = Math.min(state.page, totalPages);
  const pageRows = useMemo(
    () => sorted.slice((effectivePage - 1) * state.size, effectivePage * state.size),
    [sorted, effectivePage, state.size],
  );

  const selectedMarket = useMemo(
    () => (markets.data?.markets ?? []).find((market) => market.symbol === selectedSymbol) ?? null,
    [markets.data, selectedSymbol],
  );

  const handleSelectRow = (symbol: string) => {
    setSelectedSymbol((current) => (current === symbol ? null : symbol));
  };

  if (markets.isLoading) {
    return <MarketsSkeleton />;
  }

  if (markets.isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={<Button onClick={() => markets.refetch()}>Retry</Button>}
      >
        Failed to load markets: {markets.error.message}
      </Alert>
    );
  }

  if (!markets.data || markets.data.markets.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 6, textAlign: 'center' }}>
        <Typography variant="h6" component="h2" gutterBottom>
          No markets available
        </Typography>
        <Typography variant="body2" color="text.secondary">
          The platform is not tracking any markets yet. Market synchronization will populate this
          directory.
        </Typography>
      </Paper>
    );
  }

  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, lg: 8 }}>
        <Stack spacing={2}>
          <MarketsToolbar
            search={state.q}
            onSearchChange={setSearch}
            type={state.type}
            status={state.status}
            exchange={state.exchange}
            exchanges={exchanges}
            onFilterChange={setFilter}
            hasFilters={state.hasFilters}
            onClearFilters={clearFilters}
          />
          <MarketsTable
            rows={pageRows}
            total={sorted.length}
            sort={state.sort}
            dir={state.dir}
            onSort={toggleSort}
            page={effectivePage}
            size={state.size}
            onPageChange={changePage}
            onSizeChange={changeSize}
            selectedSymbol={selectedSymbol}
            onSelectRow={handleSelectRow}
          />
          <Typography variant="caption" color="text.secondary">
            {sorted.length} of {markets.data.total} markets match the current filters.
          </Typography>
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, lg: 4 }}>
        {selectedMarket ? (
          <DetailPanel market={selectedMarket} />
        ) : (
          <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Select a market to view details.
            </Typography>
          </Paper>
        )}
      </Grid>
    </Grid>
  );
}
