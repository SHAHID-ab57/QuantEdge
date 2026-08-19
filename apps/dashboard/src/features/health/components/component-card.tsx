'use client';

import type { SvgIconComponent } from '@mui/icons-material';
import ApiIcon from '@mui/icons-material/Api';
import AltRouteIcon from '@mui/icons-material/AltRoute';
import HttpIcon from '@mui/icons-material/Http';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import WifiIcon from '@mui/icons-material/Wifi';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ComponentStatus, DeltaConnectionState } from '@/types/api/system';
import { useNow } from '../hooks/use-now';
import { formatLatency, formatNumber, formatRelative } from '../lib/format';
import { Metric, STATUS_COLOR, StatusPill } from './primitives';

const ICONS: Record<string, SvgIconComponent> = {
  api: ApiIcon,
  database: StorageIcon,
  delta_rest: HttpIcon,
  delta_ws: WifiIcon,
  event_bus: AltRouteIcon,
  state_manager: MemoryIcon,
};

const DISPLAY_NAMES: Record<string, string> = {
  delta_rest: 'Delta REST',
  delta_ws: 'Delta WebSocket',
  event_bus: 'Event Bus',
  state_manager: 'State Manager',
};

const ACCENT: Record<ComponentStatus['status'], string> = {
  ok: 'success.main',
  degraded: 'warning.main',
  unavailable: 'error.main',
};

function displayName(name: string): string {
  const mapped = DISPLAY_NAMES[name];
  if (mapped) {
    return mapped;
  }
  return name.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function stateLabel(component: ComponentStatus): string {
  if (component.state) {
    return component.state.replace(/^./, (char) => char.toUpperCase());
  }
  return component.status === 'ok' ? 'Operational' : 'Attention required';
}

function authLabel(deltaWs: DeltaConnectionState): string {
  if (deltaWs.public) {
    return 'Public feed';
  }
  return deltaWs.authenticated ? 'Authenticated' : 'Not authenticated';
}

export function ComponentCard({
  component,
  deltaWs,
}: Readonly<{ component: ComponentStatus; deltaWs?: DeltaConnectionState | null }>) {
  const Icon = ICONS[component.name] ?? ApiIcon;
  const title = displayName(component.name);
  const now = useNow();

  return (
    <Paper
      component="section"
      aria-labelledby={`status-title-${component.name}`}
      sx={{
        p: 2,
        height: '100%',
        borderTop: 2,
        borderTopColor: ACCENT[component.status],
        display: 'flex',
        flexDirection: 'column',
        gap: 1.5,
      }}
    >
      <Box
        sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}
      >
        <Stack direction="row" spacing={1.5} alignItems="center" minWidth={0}>
          <Box
            sx={{
              display: 'grid',
              placeItems: 'center',
              width: 40,
              height: 40,
              borderRadius: 1.5,
              bgcolor: 'action.hover',
              color: ACCENT[component.status],
              flexShrink: 0,
            }}
          >
            <Icon fontSize="small" />
          </Box>
          <Box minWidth={0}>
            <Typography
              id={`status-title-${component.name}`}
              variant="subtitle2"
              component="h3"
              noWrap
            >
              {title}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {stateLabel(component)}
            </Typography>
          </Box>
        </Stack>
        <StatusPill status={component.status} />
      </Box>

      <Box
        component="dl"
        sx={{
          m: 0,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(96px, 1fr))',
          gap: 1.5,
        }}
      >
        {component.updated_at !== undefined && component.updated_at !== null && (
          <Metric label="Last update" value={formatRelative(component.updated_at, now)} />
        )}
        {component.latency_ms !== undefined && component.latency_ms !== null && (
          <Metric
            label={component.name === 'delta_ws' ? 'Message age' : 'Latency'}
            value={formatLatency(component.latency_ms)}
          />
        )}
        {component.uptime_seconds !== undefined && component.uptime_seconds !== null && (
          <Metric label="Uptime" value={`${formatNumber(Math.floor(component.uptime_seconds))}s`} />
        )}
      </Box>

      {component.name === 'delta_ws' && deltaWs && (
        <>
          <Divider sx={{ my: 0.5 }} />
          <Stack spacing={0.5}>
            <Box
              component="dl"
              sx={{ m: 0, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.5 }}
            >
              <Metric label="Subscriptions" value={deltaWs.subscriptions.length} />
              <Metric label="Messages" value={formatNumber(deltaWs.messages_received)} />
              <Metric label="Reconnects" value={deltaWs.reconnects} />
              <Metric label="Auth" value={authLabel(deltaWs)} />
            </Box>
            <Typography variant="caption" color="text.secondary">
              Requested:{' '}
              {deltaWs.requested_subscriptions.length > 0
                ? deltaWs.requested_subscriptions.join(', ')
                : '—'}
              {deltaWs.connection_attempts > 0 ? ` · attempts ${deltaWs.connection_attempts}` : ''}
            </Typography>
          </Stack>
        </>
      )}

      {component.detail && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 'auto' }}>
          {component.detail}
        </Typography>
      )}
    </Paper>
  );
}

export function componentStatusColor(status: ComponentStatus['status']): string {
  return STATUS_COLOR[status];
}
