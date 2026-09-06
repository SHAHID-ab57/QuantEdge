'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import PublicOffIcon from '@mui/icons-material/PublicOff';
import { EmptyStateNotice } from '@/components/empty-state-notice';
import { Section } from '@/components/section';
import { ConnectorCard } from './components/connector-card';
import { PlannedDataSources } from './components/planned-data-sources';
import { useConnectorCatalog } from './hooks/use-connector-data';

function ActiveDataSourcesSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading data sources">
      <Skeleton variant="rounded" height={140} />
      <Skeleton variant="rounded" height={140} />
    </Stack>
  );
}

/**
 * The Data Sources page (M4-E1-T3, `ARCHITECTURE.md` § "External Data
 * Connectors" → "Data Sources Page"): visibility into what external data
 * this platform has actually ingested, and what's coming next in
 * Milestone 4 — without querying the database directly.
 *
 * "Active Data Sources" is entirely registry-driven (`GET /connectors`):
 * a source registered on the backend appears here with no change to this
 * page, the same guarantee the Feature Engineering page's own
 * `FeatureSelector` already gives `/features`. "Planned Data Sources" is
 * the deliberate exception — a static, hardcoded list of what hasn't
 * shipped yet (see `lib/planned-connectors.ts`), since there is nothing
 * in the registry for an unbuilt connector to read.
 */
function ActiveDataSources() {
  const catalog = useConnectorCatalog();

  if (catalog.isLoading) {
    return <ActiveDataSourcesSkeleton />;
  }

  if (catalog.isError) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={<Button onClick={() => catalog.refetch()}>Retry</Button>}
      >
        Failed to load data sources: {catalog.error.message}
      </Alert>
    );
  }

  if (!catalog.data || catalog.data.connectors.length === 0) {
    return (
      <EmptyStateNotice
        icon={<PublicOffIcon fontSize="small" color="disabled" />}
        title="No data sources registered yet"
        description="No external data connector is registered on the backend yet."
      />
    );
  }

  return (
    <Grid container spacing={2}>
      {catalog.data.connectors.map((connector) => (
        <Grid key={connector.source} size={{ xs: 12, sm: 6, md: 4 }}>
          <ConnectorCard connector={connector} />
        </Grid>
      ))}
    </Grid>
  );
}

export function DataSourcesPage() {
  return (
    <Stack spacing={3}>
      <Section title="Active Data Sources" subtitle="Ingested external data, updated live">
        <ActiveDataSources />
      </Section>

      <Section
        title="Planned Data Sources"
        subtitle="Named in Milestone 4 (Data Breadth), not yet built"
      >
        <PlannedDataSources />
      </Section>
    </Stack>
  );
}
