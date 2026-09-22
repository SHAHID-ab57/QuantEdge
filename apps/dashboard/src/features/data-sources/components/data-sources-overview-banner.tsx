'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { Connector, ConnectorHealthStatus } from '@/types/api/connectors';

export type OverviewStatus = 'healthy' | 'partial' | 'critical';

/** Rolls every connector's own `health_status` up to one page-level status —
 * mirrors `overallStatus` in `features/health/components/overall-status-banner.tsx`
 * exactly (`failing` anywhere -> critical; `stale`/`never_ingested` anywhere,
 * with no `failing` -> partial; otherwise healthy). A brand-new connector that
 * hasn't synced yet reads as `partial`, not `healthy` — it genuinely has
 * nothing to show, which is a real gap, just not an urgent one. */
export function overviewStatus(connectors: readonly Connector[]): OverviewStatus {
  if (connectors.some((connector) => connector.health_status === 'failing')) {
    return 'critical';
  }
  if (
    connectors.some(
      (connector) =>
        connector.health_status === 'stale' || connector.health_status === 'never_ingested',
    )
  ) {
    return 'partial';
  }
  return 'healthy';
}

const OVERVIEW_META: Record<
  OverviewStatus,
  { color: 'success' | 'warning' | 'error'; label: string; dot: string }
> = {
  healthy: { color: 'success', label: 'All sources healthy', dot: '#2e7d32' },
  partial: { color: 'warning', label: 'Some sources need attention', dot: '#ed6c02' },
  critical: { color: 'error', label: 'A source is failing', dot: '#d32f2f' },
};

const STATUS_ORDER: ConnectorHealthStatus[] = ['healthy', 'stale', 'failing', 'never_ingested'];
const STATUS_CHIP_LABEL: Record<ConnectorHealthStatus, string> = {
  healthy: 'Healthy',
  stale: 'Stale',
  failing: 'Failing',
  never_ingested: 'Never ingested',
};
const STATUS_CHIP_COLOR: Record<
  ConnectorHealthStatus,
  'success' | 'warning' | 'error' | 'default'
> = {
  healthy: 'success',
  stale: 'warning',
  failing: 'error',
  never_ingested: 'default',
};

function countBy(connectors: readonly Connector[], status: ConnectorHealthStatus): number {
  return connectors.filter((connector) => connector.health_status === status).length;
}

export interface DataSourcesOverviewBannerProps {
  connectors: readonly Connector[];
  lastRefreshedAt: number | undefined;
}

/**
 * The page's own headline strip — what "Active Data Sources" adds up to at a
 * glance, before scanning individual cards. Mirrors the Health page's
 * `OverallStatusBanner` deliberately (same colored-`Paper`-plus-pulsing-dot
 * shape, `bgcolor: '{color}.dark'`) so a person moving between the two pages
 * reads "is something wrong" the same way in both places, rather than this
 * page inventing its own visual vocabulary for the identical question.
 *
 * The one figure genuinely new to this page — total points ever ingested,
 * summed across every connector's own `total_points` — is the thing a bare
 * list of cards can't show at all: not "here are 8 sources" but "here is
 * how much this platform has actually accumulated," which is what makes
 * this feel like a running system rather than a static settings page.
 */
export function DataSourcesOverviewBanner({
  connectors,
  lastRefreshedAt,
}: Readonly<DataSourcesOverviewBannerProps>) {
  const status = overviewStatus(connectors);
  const meta = OVERVIEW_META[status];
  const totalPoints = connectors.reduce((sum, connector) => sum + connector.total_points, 0);

  return (
    <Paper
      component="section"
      aria-label="Data sources overview"
      sx={{
        p: 2.5,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 2,
        flexWrap: 'wrap',
        bgcolor: `${meta.color}.dark`,
        color: `${meta.color}.contrastText`,
      }}
    >
      <Stack direction="row" spacing={2} alignItems="center">
        <Box
          aria-hidden
          sx={{
            width: 14,
            height: 14,
            borderRadius: '50%',
            bgcolor: 'common.white',
            boxShadow: `0 0 0 4px ${meta.dot}`,
            animation: status === 'healthy' ? 'data-sources-pulse 2s infinite' : undefined,
            '@keyframes data-sources-pulse': {
              '0%': { boxShadow: `0 0 0 0 ${meta.dot}66` },
              '70%': { boxShadow: `0 0 0 10px ${meta.dot}00` },
              '100%': { boxShadow: `0 0 0 0 ${meta.dot}00` },
            },
          }}
        />
        <Box>
          <Typography variant="h6" component="h2" fontWeight={700}>
            {meta.label}
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.9 }}>
            {new Intl.NumberFormat().format(totalPoints)} data points tracked across{' '}
            {connectors.length} live {connectors.length === 1 ? 'source' : 'sources'}
          </Typography>
        </Box>
      </Stack>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        {STATUS_ORDER.map((statusKey) => {
          const count = countBy(connectors, statusKey);
          if (count === 0) {
            return null;
          }
          return (
            <Chip
              key={statusKey}
              size="small"
              color={STATUS_CHIP_COLOR[statusKey]}
              variant={statusKey === 'healthy' ? 'filled' : 'outlined'}
              label={`${STATUS_CHIP_LABEL[statusKey]}: ${count}`}
              sx={
                statusKey === 'healthy'
                  ? undefined
                  : { color: 'inherit', borderColor: 'rgba(255,255,255,0.5)' }
              }
            />
          );
        })}
        <Chip
          size="small"
          variant="outlined"
          label="Auto-refresh every 30s"
          aria-label="Auto-refresh every 30 seconds"
          sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.5)' }}
        />
        {lastRefreshedAt !== undefined && (
          <Chip
            size="small"
            variant="outlined"
            label={`Updated ${new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(new Date(lastRefreshedAt))}`}
            aria-label={`Last refreshed at ${new Date(lastRefreshedAt).toISOString()}`}
            sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.5)' }}
          />
        )}
      </Stack>
    </Paper>
  );
}
