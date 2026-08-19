'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { SystemHealth } from '@/types/api/system';
import { formatDateTime } from '../lib/format';

const COMPONENT_ORDER = [
  'api',
  'database',
  'delta_rest',
  'delta_ws',
  'event_bus',
  'state_manager',
] as const;

export type OverallStatus = 'healthy' | 'partial' | 'critical';

export function overallStatus(health: SystemHealth, liveEnabled: boolean): OverallStatus {
  const relevant = COMPONENT_ORDER.map((name) => health[name]).filter(
    (component) => !(component.name === 'delta_ws' && component.state === 'stopped'),
  );
  if (relevant.some((component) => component.status === 'unavailable')) {
    return 'critical';
  }
  if (relevant.some((component) => component.status === 'degraded')) {
    return 'partial';
  }
  if (!liveEnabled && health.delta_ws.state === 'stopped') {
    return 'healthy';
  }
  return 'healthy';
}

const OVERALL_META: Record<
  OverallStatus,
  { color: 'success' | 'warning' | 'error'; label: string; blurb: string; dot: string }
> = {
  healthy: {
    color: 'success',
    label: 'Healthy',
    blurb: 'All monitored components are operational',
    dot: '#2e7d32',
  },
  partial: {
    color: 'warning',
    label: 'Partially Operational',
    blurb: 'Some components need attention',
    dot: '#ed6c02',
  },
  critical: {
    color: 'error',
    label: 'Critical',
    blurb: 'Components are down',
    dot: '#d32f2f',
  },
};

export function OverallStatusBanner({
  health,
  liveEnabled,
  lastRefreshedAt,
}: Readonly<{
  health: SystemHealth;
  liveEnabled: boolean;
  lastRefreshedAt: number | undefined;
}>) {
  const overall = overallStatus(health, liveEnabled);
  const meta = OVERALL_META[overall];
  const okCount = COMPONENT_ORDER.filter((name) => health[name].status === 'ok').length;

  return (
    <Paper
      component="section"
      aria-label="Overall platform status"
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
            animation: overall === 'healthy' ? 'pulse 2s infinite' : undefined,
            '@keyframes pulse': {
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
            {meta.blurb} · {okCount} of {COMPONENT_ORDER.length} components OK
          </Typography>
        </Box>
      </Stack>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <Chip
          size="small"
          color={meta.color}
          variant="outlined"
          label="Auto-refresh every 10s"
          aria-label="Auto-refresh every 10 seconds"
          sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.5)' }}
        />
        {lastRefreshedAt !== undefined && (
          <Chip
            size="small"
            variant="outlined"
            label={`Updated ${formatDateTime(new Date(lastRefreshedAt).toISOString())}`}
            aria-label={`Last refreshed at ${new Date(lastRefreshedAt).toISOString()}`}
            sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.5)' }}
          />
        )}
      </Stack>
    </Paper>
  );
}
