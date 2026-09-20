'use client';

import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha, type SxProps, type Theme } from '@mui/material/styles';
import { StatTile } from '@/components/stat-tile';
import { Sparkline } from '@/features/trades/components/sparkline';
import type { Connector, ConnectorHealthStatus } from '@/types/api/connectors';
import { HISTORY_SPARKLINE_LIMIT, useConnectorHistory } from '../hooks/use-connector-data';
import { formatConnectorValue, formatLastUpdated } from '../lib/format';

const HEALTH_COLOR: Record<ConnectorHealthStatus, 'success' | 'warning' | 'error' | 'default'> = {
  healthy: 'success',
  stale: 'warning',
  failing: 'error',
  never_ingested: 'default',
};

const HEALTH_LABEL: Record<ConnectorHealthStatus, string> = {
  healthy: 'Healthy',
  stale: 'Stale',
  failing: 'Failing',
  never_ingested: 'Never ingested',
};

/**
 * The card's own treatment by health. The corner pill alone is a small
 * label: without this, a failing connector's card looked identical to a
 * healthy one, and a problem could sit unnoticed in a grid of cards.
 *
 * `failing` gets a red border plus an outer 1px ring (effectively a 2px
 * edge, but drawn outside the box so the card never changes size and the
 * grid never shifts) and a faint red wash. `stale` is deliberately quieter:
 * a muted amber edge and the faintest wash, since it is a slower, less
 * urgent problem than a connector that is erroring right now. `healthy` and
 * `never_ingested` are left exactly as before, so the tinted cards stand out
 * against a mostly-untinted page rather than everything competing.
 */
function healthCardSx(status: ConnectorHealthStatus): SxProps<Theme> {
  switch (status) {
    case 'failing':
      return (theme) => ({
        borderColor: theme.palette.error.main,
        boxShadow: `0 0 0 1px ${theme.palette.error.main}`,
        backgroundColor: alpha(theme.palette.error.main, 0.08),
      });
    case 'stale':
      return (theme) => ({
        borderColor: alpha(theme.palette.warning.main, 0.7),
        backgroundColor: alpha(theme.palette.warning.main, 0.04),
      });
    default:
      return {};
  }
}

/**
 * A connector's health status, matching `StatusPill`'s own convention in
 * `features/health/components/primitives.tsx` (small `Chip`, one of a
 * fixed set of colors/labels keyed by status) — not imported directly,
 * since that one is typed to `ComponentStatus['status']`
 * (ok/degraded/unavailable), a different, unrelated status vocabulary.
 */
function HealthPill({ status }: Readonly<{ status: ConnectorHealthStatus }>) {
  return (
    <Chip
      size="small"
      color={HEALTH_COLOR[status]}
      label={HEALTH_LABEL[status]}
      sx={{ fontWeight: 700, letterSpacing: '0.04em' }}
    />
  );
}

export interface ConnectorCardProps {
  connector: Connector;
}

/**
 * One registered connector's card — current value, a trend sparkline over
 * its own recent history, and a last-updated caption. Fetches its own
 * history independently (rather than the page fetching every connector's
 * history up front) so a slow or failing history request for one source
 * never blocks another card from rendering its current value.
 *
 * Reuses `Sparkline` (`features/trades/components/sparkline.tsx`) — the
 * same tiny, dependency-free SVG line the Trade Analytics dashboard uses
 * for a rolling VWAP trend, rather than a second small-chart
 * implementation for what is, at this scale, the same problem.
 */
export function ConnectorCard({ connector }: ConnectorCardProps) {
  const historyQuery = useConnectorHistory(connector.source, {
    limit: HISTORY_SPARKLINE_LIMIT,
  });
  const values = historyQuery.data?.items.map((item) => item.value) ?? [];
  const titleId = `connector-${connector.source}-title`;
  const healthSx = healthCardSx(connector.health_status);

  return (
    <Paper
      component="section"
      aria-labelledby={titleId}
      data-health-status={connector.health_status}
      sx={[{ p: 2, height: '100%' }, ...(Array.isArray(healthSx) ? healthSx : [healthSx])]}
    >
      <Stack spacing={0.5}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Typography id={titleId} variant="subtitle1" component="h3">
            {connector.label}
          </Typography>
          <HealthPill status={connector.health_status} />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {connector.description}
        </Typography>
      </Stack>
      <Stack
        direction="row"
        spacing={2}
        alignItems="center"
        justifyContent="space-between"
        sx={{ mt: 2 }}
      >
        <StatTile
          label="Current value"
          value={formatConnectorValue(connector.latest_value)}
          caption={formatLastUpdated(connector.latest_timestamp)}
          emphasis
        />
        <Sparkline
          values={values}
          ariaLabel={`${connector.label} recent trend`}
          color="var(--mui-palette-info-main)"
          width={140}
          height={40}
        />
      </Stack>
    </Paper>
  );
}
