'use client';

import MemoryIcon from '@mui/icons-material/Memory';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { SystemMetrics, SystemStatus } from '@/types/api/system';
import { useNow } from '../hooks/use-now';
import { formatDateTime, formatLatency, formatNumber, formatRelative } from '../lib/format';
import { Metric, MetricRow } from './primitives';

function priceLabel(symbol: string): string {
  const upper = symbol.toUpperCase();
  if (upper.startsWith('BTC')) {
    return `BTC ${upper.slice(3) || 'USD'}`;
  }
  if (upper.startsWith('ETH')) {
    return `ETH ${upper.slice(3) || 'USD'}`;
  }
  return upper;
}

export function StateCard({
  metrics,
  status,
}: Readonly<{ metrics: SystemMetrics; status: SystemStatus }>) {
  const now = useNow();
  const prices = Object.entries(metrics.state_latest_prices).sort(([a], [b]) => {
    const rank = (symbol: string): number => {
      if (symbol.startsWith('BTC')) {
        return 0;
      }
      if (symbol.startsWith('ETH')) {
        return 1;
      }
      return 2;
    };
    return rank(a) - rank(b);
  });

  return (
    <Paper component="section" aria-labelledby="state-title" sx={{ p: 2, height: '100%' }}>
      <Typography
        id="state-title"
        variant="subtitle1"
        component="h3"
        sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
      >
        <MemoryIcon fontSize="small" color="action" />
        State Manager
      </Typography>

      <Box
        component="dl"
        sx={{
          m: 0,
          mt: 1.5,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: 2,
        }}
      >
        <Metric label="Tracked symbols" value={formatNumber(status.symbols_tracked)} />
        <Metric label="Latest update" value={formatRelative(metrics.state_latest_update_at, now)} />
        <Metric
          label="Update latency"
          value={formatLatency(metrics.state_average_update_latency_ms ?? null)}
        />
      </Box>

      <Box sx={{ mt: 1.5 }}>
        <Typography
          variant="caption"
          component="h4"
          color="text.secondary"
          sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}
        >
          Latest prices
        </Typography>
        {prices.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            No prices yet — waiting for live market data
          </Typography>
        ) : (
          <Stack spacing={0.25} sx={{ mt: 0.5 }}>
            {prices.slice(0, 4).map(([symbol, price]) => (
              <MetricRow key={symbol} label={priceLabel(symbol)} value={price} tone="ok" />
            ))}
          </Stack>
        )}
      </Box>

      <Box component="dl" sx={{ m: 0, mt: 1 }}>
        <MetricRow
          label="Order books cached"
          value={formatNumber(metrics.state_order_books_cached)}
        />
        <MetricRow label="Trades cached" value={formatNumber(metrics.state_trades_cached)} />
        <MetricRow label="Tickers cached" value={formatNumber(metrics.state_tickers_cached)} />
        <MetricRow label="Candles cached" value={formatNumber(metrics.state_candles_cached)} />
        <MetricRow
          label="Cache hit ratio"
          value={
            metrics.cache_hits + metrics.cache_misses === 0
              ? '—'
              : `${((metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses)) * 100).toFixed(0)}%`
          }
        />
      </Box>
      {metrics.state_latest_update_at && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {formatDateTime(metrics.state_latest_update_at)}
        </Typography>
      )}
    </Paper>
  );
}
