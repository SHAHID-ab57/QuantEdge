'use client';

import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined';
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
import { useEffect, useState } from 'react';
import type { Market, ResearchTimeframeMetrics } from '@/types/api/market';
import { useSystemStatus } from '@/features/health/hooks/use-system-data';
import { useMarketDetail, useTimeframeResearch } from '../hooks/use-markets-data';
import { useNow } from '../hooks/use-now';
import {
  formatDateTime,
  formatFundingInterval,
  formatNumber,
  formatPrice,
  formatRelative,
} from '../lib/format';
import { computeQualityScore, type QualityInput } from '../lib/quality';
import { sortTimeframes } from '../lib/timeframes';
import { DataQuality } from './data-quality';
import { LiveStatus } from './live-status';

interface DetailPanelProps {
  market: Market;
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="overline"
      color="text.secondary"
      component="h3"
      sx={{ display: 'block', mb: 0.5 }}
    >
      {children}
    </Typography>
  );
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
      <Skeleton variant="rounded" height={72} />
      <Skeleton variant="rounded" height={120} />
      <Skeleton variant="rounded" height={80} />
      <Skeleton variant="rounded" height={80} />
      <Skeleton variant="rounded" height={56} />
    </Stack>
  );
}

function completenessColor(completeness: number | null): 'success' | 'warning' {
  if (completeness !== null && completeness >= 95) {
    return 'success';
  }
  return 'warning';
}

function ResearchMetrics({ research }: { research: ResearchTimeframeMetrics }) {
  return (
    <>
      <DetailRow label="Oldest candle">{formatDateTime(research.oldest_at)}</DetailRow>
      <DetailRow label="Newest candle">{formatDateTime(research.newest_at)}</DetailRow>
      <DetailRow label="Coverage duration">
        {research.coverage_days !== null ? `${research.coverage_days.toFixed(1)}d` : '—'}
      </DetailRow>
      <DetailRow label="Stored candles">{formatNumber(research.stored_candles)}</DetailRow>
      <DetailRow label="Expected candles">{formatNumber(research.expected_candles)}</DetailRow>
      <DetailRow label="Missing candles">
        <Box
          component="span"
          sx={{
            color: research.missing_candles > 0 ? 'warning.main' : 'inherit',
          }}
        >
          {formatNumber(research.missing_candles)}
        </Box>
      </DetailRow>
      <DetailRow label="Average daily candles">
        {research.average_daily_candles !== null ? research.average_daily_candles.toFixed(1) : '—'}
      </DetailRow>
      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            Data completeness
          </Typography>
          <Typography variant="body2">
            {research.completeness !== null ? `${research.completeness.toFixed(1)}%` : '—'}
          </Typography>
        </Stack>
        <LinearProgress
          variant="determinate"
          value={research.completeness ?? 0}
          color={completenessColor(research.completeness)}
          aria-label={`Data completeness ${research.completeness}%`}
          sx={{ height: 8, borderRadius: 4 }}
        />
      </Stack>
    </>
  );
}

export function DetailPanel({ market }: DetailPanelProps) {
  const now = useNow(1_000);
  const detail = useMarketDetail(market.symbol);
  const status = useSystemStatus();
  const [selectedTimeframe, setSelectedTimeframe] = useState<string | null>(null);

  useEffect(() => {
    setSelectedTimeframe(null);
  }, [market.symbol]);

  const timeframes = sortTimeframes(detail.data?.timeframes ?? []);
  const selectedIsAvailable = selectedTimeframe !== null && timeframes.includes(selectedTimeframe);
  const effectiveTimeframe = selectedIsAvailable
    ? selectedTimeframe
    : (detail.data?.primaryTimeframe ?? timeframes[0] ?? null);
  const research = useTimeframeResearch(market.symbol, effectiveTimeframe);

  const qualityInput: QualityInput | null = detail.data
    ? {
        timeframes: detail.data.timeframes,
        totalCandles: detail.data.totalCandles,
        lastSyncAt: detail.data.lastSyncAt,
        now,
      }
    : null;

  const score = qualityInput ? computeQualityScore(qualityInput) : null;
  const wsConnected = status.data?.delta_ws_connected ?? false;

  return (
    <Paper
      variant="outlined"
      sx={{ p: 2.5 }}
      role="region"
      aria-label={`Details for ${market.symbol}`}
    >
      <Stack spacing={2}>
        <Box component="section" aria-label="Market overview">
          <SectionHeading>Market overview</SectionHeading>
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
          {detail.data && detail.data.timeframes.length > 0 ? (
            <>
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mt: 1 }}>
                <Typography variant="h5" component="p" fontWeight={600}>
                  {formatPrice(detail.data.latestPrice)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  latest close ({detail.data.primaryTimeframe ?? '—'})
                </Typography>
              </Box>
              <Stack component="dl" spacing={1} sx={{ m: 0, mt: 1 }}>
                <DetailRow label="Latest candle time">
                  {formatRelative(detail.data.latestCandleTime, now)}
                </DetailRow>
                <DetailRow label="Last synchronization">
                  {formatRelative(detail.data.lastSyncAt, now)}
                </DetailRow>
                <DetailRow label="Candle count">{formatNumber(detail.data.totalCandles)}</DetailRow>
              </Stack>
            </>
          ) : null}
        </Box>

        <Divider />

        <Box component="section" aria-label="Live status section">
          <SectionHeading>Live status</SectionHeading>
          <LiveStatus
            now={now}
            wsConnected={wsConnected}
            lastWsMessageAt={status.data?.last_ws_message_at ?? null}
            latestCandleTime={detail.data?.latestCandleTime ?? null}
            lastIngestionAt={status.data?.last_ingestion_at ?? null}
          />
        </Box>

        <Divider />

        {detail.isLoading ? <DetailSkeleton /> : null}

        {detail.isError ? (
          <Alert severity="error" role="alert">
            Failed to load details for {market.symbol}.
          </Alert>
        ) : null}

        {detail.data ? (
          <>
            {detail.data.timeframes.length === 0 ? (
              <Box sx={{ textAlign: 'center', py: 3 }} role="status" aria-label="No candles stored">
                <StorageOutlinedIcon color="disabled" sx={{ fontSize: 48 }} />
                <Typography variant="body1" sx={{ mt: 1 }}>
                  No stored candles yet
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  The candle sync scheduler will backfill history for this market.
                </Typography>
              </Box>
            ) : (
              <>
                <Box component="section" aria-label="Timeframes section">
                  <SectionHeading>Timeframes</SectionHeading>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
                    {timeframes.map((timeframe) => {
                      const count =
                        detail.data?.candleCounts.find((entry) => entry.timeframe === timeframe)
                          ?.count ?? 0;
                      const isSelected = timeframe === effectiveTimeframe;
                      return (
                        <Tooltip
                          key={timeframe}
                          title={`${formatNumber(count)} stored candles`}
                          arrow
                        >
                          <Chip
                            label={`${timeframe} · ${formatNumber(count)}`}
                            size="small"
                            color={isSelected ? 'primary' : 'default'}
                            variant={isSelected ? 'filled' : 'outlined'}
                            onClick={() => setSelectedTimeframe(timeframe)}
                            aria-pressed={isSelected}
                            aria-label={`Timeframe ${timeframe}, ${formatNumber(count)} candles`}
                          />
                        </Tooltip>
                      );
                    })}
                  </Box>
                </Box>

                <Box component="section" aria-label="Research metrics section">
                  <SectionHeading>Research metrics · {effectiveTimeframe ?? '—'}</SectionHeading>
                  {research === undefined ? <Skeleton variant="rounded" height={160} /> : null}
                  {research === null ? (
                    <Typography variant="body2" color="text.secondary">
                      No research metrics for {effectiveTimeframe}.
                    </Typography>
                  ) : null}
                  {research !== null && research !== undefined ? (
                    <Stack component="dl" spacing={1} sx={{ m: 0 }}>
                      <ResearchMetrics research={research} />
                    </Stack>
                  ) : null}
                </Box>

                <Divider />

                <Box component="section" aria-label="Data quality section">
                  <DataQuality
                    score={score}
                    qualityInput={qualityInput}
                    calculatedFrom={formatDateTime(detail.data.latestCandleTime)}
                    onRecalculate={() => detail.refetch()}
                    isRefetching={detail.isFetching}
                  />
                </Box>

                <Divider />

                <Box component="section" aria-label="Contract metadata section">
                  <SectionHeading>Contract metadata</SectionHeading>
                  <Stack component="dl" spacing={1} sx={{ m: 0 }}>
                    <DetailRow label="Exchange ID">
                      <Box
                        component="span"
                        sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}
                        title={market.exchange_id}
                      >
                        {market.exchange_id.slice(0, 8)}…
                      </Box>
                    </DetailRow>
                    <DetailRow label="Symbol ID">
                      {market.delta_product_id !== null ? (
                        <Box component="span" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                          {market.delta_product_id}
                        </Box>
                      ) : (
                        '—'
                      )}
                    </DetailRow>
                    <DetailRow label="Contract type">
                      {market.delta_contract_type ?? market.market_type}
                    </DetailRow>
                    <DetailRow label="Tick size">{market.tick_size ?? '—'}</DetailRow>
                    <DetailRow label="Contract size">—</DetailRow>
                    <DetailRow label="Price precision">—</DetailRow>
                    <DetailRow label="Quantity precision">—</DetailRow>
                    <DetailRow label="Funding">
                      {market.market_type === 'perpetual'
                        ? `${formatFundingInterval(market.funding_interval_seconds)}${
                            market.funding_method ? ` · ${market.funding_method}` : ''
                          }`
                        : '—'}
                    </DetailRow>
                    <DetailRow label="Listing date">
                      {market.listing_date ? formatDateTime(market.listing_date) : '—'}
                    </DetailRow>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    Contract size, price precision, and quantity precision are not published by
                    Delta Exchange.
                  </Typography>
                </Box>
              </>
            )}
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
