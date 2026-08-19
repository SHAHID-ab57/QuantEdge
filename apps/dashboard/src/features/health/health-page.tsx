'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import { BusCard } from './components/bus-card';
import { ComponentCard } from './components/component-card';
import { DatabaseCard } from './components/database-card';
import { OverallStatusBanner } from './components/overall-status-banner';
import { PlatformCard } from './components/platform-card';
import { ProcessingCard } from './components/processing-card';
import { StateCard } from './components/state-card';
import { TimelineCard } from './components/timeline-card';
import { useSystemHealth, useSystemMetrics, useSystemStatus } from './hooks/use-system-data';

const COMPONENT_ORDER = [
  'api',
  'database',
  'delta_rest',
  'delta_ws',
  'event_bus',
  'state_manager',
] as const;

function HealthSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading health data">
      <Skeleton variant="rounded" height={88} />
      <Grid container spacing={2}>
        {Array.from({ length: 6 }, (_, index) => (
          <Grid key={index} size={{ xs: 12, sm: 6, lg: 4 }}>
            <Skeleton variant="rounded" height={168} />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        {Array.from({ length: 6 }, (_, index) => (
          <Grid key={index} size={{ xs: 12, md: 6 }}>
            <Skeleton variant="rounded" height={180} />
          </Grid>
        ))}
      </Grid>
    </Stack>
  );
}

export function HealthPage() {
  const health = useSystemHealth();
  const status = useSystemStatus();
  const metrics = useSystemMetrics();

  const isLoading = health.isLoading || status.isLoading || metrics.isLoading;
  const isError = health.isError || status.isError || metrics.isError;

  if (isError) {
    const message = health.error?.message ?? status.error?.message ?? metrics.error?.message;
    return (
      <Alert
        severity="error"
        action={
          <Button
            color="inherit"
            onClick={() =>
              void Promise.all([health.refetch(), status.refetch(), metrics.refetch()])
            }
          >
            Try again
          </Button>
        }
      >
        <AlertTitle>Unable to load platform health</AlertTitle>
        <Box component="pre" sx={{ m: 0, fontSize: 12, overflow: 'auto' }}>
          {message ?? 'Unknown error'}
        </Box>
      </Alert>
    );
  }

  if (isLoading || !health.data || !status.data || !metrics.data) {
    return <HealthSkeleton />;
  }

  const noData =
    metrics.data.synchronized_markets === null &&
    metrics.data.stored_candles === null &&
    !status.data.market_data_live;

  return (
    <>
      <OverallStatusBanner
        health={health.data}
        liveEnabled={status.data.market_data_live}
        lastRefreshedAt={health.dataUpdatedAt}
      />
      {noData && (
        <Alert severity="info" sx={{ mt: 2 }}>
          No data recorded yet. Enable live market data with <code>MARKET_DATA_LIVE=true</code> on
          the API to stream WebSocket messages.
        </Alert>
      )}
      <Grid container spacing={2} sx={{ mt: 0.5 }} role="list" aria-label="Component status">
        {COMPONENT_ORDER.map((name) => (
          <Grid key={name} size={{ xs: 12, sm: 6, lg: 4 }} role="listitem">
            <ComponentCard component={health.data[name]} deltaWs={status.data.delta_ws} />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2} sx={{ mt: 0.5 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <PlatformCard status={status.data} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <DatabaseCard metrics={metrics.data} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <TimelineCard status={status.data} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ProcessingCard metrics={metrics.data} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <StateCard metrics={metrics.data} status={status.data} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <BusCard metrics={metrics.data} />
        </Grid>
      </Grid>
    </>
  );
}
