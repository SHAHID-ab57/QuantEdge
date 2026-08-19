'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { Market } from '@/types/api/market';
import { useNow } from '../hooks/use-now';
import { useMarketDetail } from '../hooks/use-markets-data';
import { formatDateTime, formatNumber, formatPrice, formatRelative } from '../lib/format';
import { computeQualityScore, QUALITY_BREAKDOWN, qualityLabel } from '../lib/quality';

interface DetailPanelProps {
  market: Market;
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={2}>
      <Typography variant="body2" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography variant="body2" component="dd" sx={{ textAlign: 'right' }}>
        {children}
      </Typography>
    </Stack>
  );
}

function DetailSkeleton() {
  return (
    <Stack spacing={1.5} role="status" aria-label="Loading market details">
      <Skeleton variant="rounded" height={64} />
      <Skeleton variant="rounded" height={120} />
      <Skeleton variant="rounded" height={80} />
      <Skeleton variant="rounded" height={56} />
    </Stack>
  );
}

function scoreColor(score: number | null): 'success' | 'warning' | 'error' {
  if (score !== null && score >= 80) {
    return 'success';
  }
  if (score !== null && score >= 50) {
    return 'warning';
  }
  return 'error';
}

export function DetailPanel({ market }: DetailPanelProps) {
  const now = useNow(1_000);
  const detail = useMarketDetail(market.symbol);

  const score = detail.data
    ? computeQualityScore({
        timeframes: detail.data.timeframes,
        totalCandles: detail.data.totalCandles,
        lastSyncAt: detail.data.lastSyncAt,
        now,
      })
    : null;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label={`Details for ${market.symbol}`}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
          <Box>
            <Typography variant="h6" component="h2">
              {market.symbol}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {market.exchange} · {market.base_asset}/{market.quote_asset} · {market.market_type}
            </Typography>
          </Box>
          <Chip
            label={market.is_active ? 'Active' : 'Inactive'}
            color={market.is_active ? 'success' : 'default'}
            size="small"
            variant="outlined"
          />
        </Stack>

        <Divider />

        {detail.isLoading ? <DetailSkeleton /> : null}

        {detail.isError ? (
          <Alert severity="error" role="alert">
            Failed to load details for {market.symbol}.
          </Alert>
        ) : null}

        {detail.data ? (
          <>
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
              <Typography variant="h5" component="p" fontWeight={600}>
                {formatPrice(detail.data.latestPrice)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                latest close ({detail.data.primaryTimeframe ?? '—'})
              </Typography>
            </Box>

            <Stack component="dl" spacing={1} sx={{ m: 0 }}>
              <DetailRow label="Latest candle time">
                {formatRelative(detail.data.latestCandleTime, now)}
              </DetailRow>
              <DetailRow label="Last synchronization">
                {formatRelative(detail.data.lastSyncAt, now)}
              </DetailRow>
              <DetailRow label="Candle count">{formatNumber(detail.data.totalCandles)}</DetailRow>
            </Stack>

            <Divider />

            <Box>
              <Typography variant="overline" color="text.secondary" component="h3">
                Available timeframes
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 0.5 }}>
                {detail.data.timeframes.length > 0 ? (
                  detail.data.timeframes.map((timeframe) => (
                    <Chip
                      key={timeframe}
                      label={timeframe}
                      size="small"
                      color={timeframe === detail.data.primaryTimeframe ? 'primary' : 'default'}
                      variant={timeframe === detail.data.primaryTimeframe ? 'filled' : 'outlined'}
                    />
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No stored candles yet.
                  </Typography>
                )}
              </Box>
            </Box>

            {detail.data.candleCounts.length > 0 ? (
              <Stack spacing={0.5}>
                {detail.data.candleCounts.map(({ timeframe, count }) => (
                  <Stack key={timeframe} direction="row" justifyContent="space-between">
                    <Typography variant="body2" color="text.secondary">
                      {timeframe}
                    </Typography>
                    <Typography variant="body2">{formatNumber(count)}</Typography>
                  </Stack>
                ))}
              </Stack>
            ) : null}

            <Divider />

            <Box>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Typography variant="overline" color="text.secondary" component="h3">
                  Data quality
                </Typography>
                <Tooltip title={QUALITY_BREAKDOWN} arrow>
                  <InfoOutlinedIcon
                    fontSize="small"
                    color="action"
                    aria-label="Data quality score explanation"
                  />
                </Tooltip>
              </Stack>
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 0.5 }}>
                <LinearProgress
                  variant="determinate"
                  value={score ?? 0}
                  color={scoreColor(score)}
                  sx={{ flexGrow: 1 }}
                  aria-label={`Data quality score ${score}`}
                />
                <Typography variant="body2" fontWeight={600}>
                  {score !== null ? `${score}/100` : '—'}
                </Typography>
                {score !== null ? (
                  <Chip
                    label={qualityLabel(score)}
                    size="small"
                    color={scoreColor(score)}
                    variant="outlined"
                  />
                ) : null}
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Last candle: {formatDateTime(detail.data.latestCandleTime)}
              </Typography>
            </Box>
          </>
        ) : null}

        {detail.isFetching && detail.isSuccess ? (
          <Box sx={{ display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={20} aria-label="Refreshing market details" />
          </Box>
        ) : null}
      </Stack>
    </Paper>
  );
}
