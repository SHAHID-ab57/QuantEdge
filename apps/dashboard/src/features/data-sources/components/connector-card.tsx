'use client';

import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import ScheduleIcon from '@mui/icons-material/Schedule';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha, type SxProps, type Theme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import { StatTile } from '@/components/stat-tile';
import { Sparkline } from '@/features/trades/components/sparkline';
import type { Connector, ConnectorHealthStatus } from '@/types/api/connectors';
import { HISTORY_SPARKLINE_LIMIT, useConnectorHistory } from '../hooks/use-connector-data';
import {
  formatAbsoluteTimestamp,
  formatConnectorValue,
  formatConnectorValueExact,
  formatInterval,
  formatLastAttempt,
  formatLastUpdated,
  formatNextSync,
} from '../lib/format';

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

/** Text color for the reason note, matching each status's own urgency —
 * `failing` red, `stale`/`never_ingested` a quieter muted tone, since only
 * `failing` is an active error happening right now. */
const HEALTH_REASON_COLOR: Record<ConnectorHealthStatus, string> = {
  healthy: 'text.secondary',
  stale: 'warning.main',
  failing: 'error.main',
  never_ingested: 'text.secondary',
};

/**
 * The plain-English reason a non-healthy status reads what it reads
 * (`app.connectors.health.describe_health`) — added after a real, live gap:
 * a bare "Stale" pill could not tell a scheduler that had stopped ticking
 * (an operational problem) apart from one still ticking on schedule
 * against a source with genuinely nothing new to report (a real,
 * non-actionable data condition). Both looked identical without this.
 * Renders nothing for `healthy` (`health_reason` is always null there).
 */
function HealthReasonNote({
  status,
  reason,
}: Readonly<{ status: ConnectorHealthStatus; reason: string | null }>) {
  if (reason === null) {
    return null;
  }
  return (
    <Stack direction="row" spacing={0.75} alignItems="flex-start" sx={{ mt: 0.5 }}>
      <InfoOutlinedIcon sx={{ fontSize: 15, mt: '1px', color: HEALTH_REASON_COLOR[status] }} />
      <Typography variant="caption" sx={{ color: HEALTH_REASON_COLOR[status] }}>
        {reason}
      </Typography>
    </Stack>
  );
}

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

/**
 * One line of the sync-status footer: an icon, a relative-time label, and a
 * tooltip carrying the exact instant — the same "relative on the surface,
 * exact one hover away" split `StatTile`'s own `hint` uses for the value
 * above it.
 */
function SyncStatusLine({
  icon,
  label,
  color,
  tooltip,
}: Readonly<{
  icon: ReactNode;
  label: string;
  color?: 'success.main' | 'warning.main' | 'error.main' | 'text.secondary';
  tooltip: string;
}>) {
  return (
    <Tooltip title={tooltip}>
      <Stack direction="row" spacing={0.75} alignItems="center">
        {icon}
        <Typography variant="caption" color={color ?? 'text.secondary'}>
          {label}
        </Typography>
      </Stack>
    </Tooltip>
  );
}

export interface ConnectorCardProps {
  connector: Connector;
}

/**
 * One registered connector's card — current value, a trend sparkline over
 * its own recent history, and a sync-status footer explaining *why* its
 * health pill reads what it reads: when it was last fetched (success or
 * failure, distinct from the value's own age — an attempt can run and find
 * nothing new), and when it's projected to be checked again. A `stale` pill
 * with no further context used to require opening the network tab to
 * understand; an overdue "Next sync" line names the actual cause (a missed
 * scheduler tick) right on the card.
 *
 * Fetches its own history independently (rather than the page fetching
 * every connector's history up front) so a slow or failing history request
 * for one source never blocks another card from rendering its current
 * value.
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

  const attempt = formatLastAttempt(connector.last_attempt_at, connector.last_attempt_success);
  const next = formatNextSync(connector.next_sync_at);
  const attemptColor = attempt.success === false ? 'error.main' : undefined;
  const attemptTooltip = connector.last_attempt_at
    ? formatAbsoluteTimestamp(connector.last_attempt_at)
    : 'The owning scheduler has not attempted this source yet';
  const nextTooltip = connector.next_sync_at
    ? formatAbsoluteTimestamp(connector.next_sync_at)
    : 'No prior attempt to project from';

  return (
    <Paper
      component="section"
      aria-labelledby={titleId}
      data-health-status={connector.health_status}
      sx={[
        { p: 2, height: '100%', display: 'flex', flexDirection: 'column' },
        ...(Array.isArray(healthSx) ? healthSx : [healthSx]),
      ]}
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
        <HealthReasonNote status={connector.health_status} reason={connector.health_reason} />
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
          hint={
            connector.latest_value !== null
              ? `Exact stored value: ${formatConnectorValueExact(connector.latest_value)}`
              : undefined
          }
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
      <Divider sx={{ my: 1.5 }} />
      <Stack spacing={0.5} sx={{ mt: 'auto' }}>
        <SyncStatusLine
          icon={
            attempt.success === false ? (
              <ErrorIcon sx={{ fontSize: 14 }} color="error" />
            ) : (
              <CheckCircleIcon
                sx={{ fontSize: 14 }}
                color={attempt.success === true ? 'success' : 'disabled'}
              />
            )
          }
          label={attempt.label}
          color={attemptColor}
          tooltip={attemptTooltip}
        />
        <SyncStatusLine
          icon={
            <ScheduleIcon sx={{ fontSize: 14 }} color={next.overdue ? 'warning' : 'disabled'} />
          }
          label={next.label}
          color={next.overdue ? 'warning.main' : undefined}
          tooltip={nextTooltip}
        />
        <Typography variant="caption" color="text.secondary">
          {new Intl.NumberFormat().format(connector.total_points)}{' '}
          {connector.total_points === 1 ? 'point' : 'points'} stored ·{' '}
          {formatInterval(connector.expected_interval_seconds)}
        </Typography>
      </Stack>
    </Paper>
  );
}
