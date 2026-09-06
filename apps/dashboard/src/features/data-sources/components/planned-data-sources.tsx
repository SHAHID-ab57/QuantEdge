'use client';

import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { PLANNED_CONNECTORS } from '../lib/planned-connectors';

/**
 * A static, hardcoded list — deliberately never backed by an API call.
 * These sources don't exist in the connector registry yet, so there is
 * nothing for this section to fetch; see `lib/planned-connectors.ts` for
 * why this list needs manual upkeep as each one ships.
 */
export function PlannedDataSources() {
  return (
    <Stack spacing={1.5}>
      {PLANNED_CONNECTORS.map((connector) => (
        <Paper
          key={connector.name}
          variant="outlined"
          sx={{
            p: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 2,
          }}
        >
          <Stack spacing={0.25}>
            <Typography variant="subtitle2">{connector.name}</Typography>
            <Typography variant="body2" color="text.secondary">
              {connector.description}
            </Typography>
          </Stack>
          <Chip size="small" label="Planned" />
        </Paper>
      ))}
    </Stack>
  );
}
