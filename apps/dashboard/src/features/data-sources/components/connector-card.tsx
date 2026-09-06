'use client';

import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { StatTile } from '@/components/stat-tile';
import { Sparkline } from '@/features/trades/components/sparkline';
import type { Connector } from '@/types/api/connectors';
import { HISTORY_SPARKLINE_LIMIT, useConnectorHistory } from '../hooks/use-connector-data';
import { formatConnectorValue, formatLastUpdated } from '../lib/format';

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

  return (
    <Paper component="section" aria-labelledby={titleId} sx={{ p: 2, height: '100%' }}>
      <Stack spacing={0.5}>
        <Typography id={titleId} variant="subtitle1" component="h3">
          {connector.label}
        </Typography>
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
