'use client';

import ReplayIcon from '@mui/icons-material/Replay';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import type { RecentCalculation } from '../lib/recent-calculations';

export interface RecentCalculationsPanelProps {
  entries: readonly RecentCalculation[];
  onRerun: (entry: RecentCalculation) => void;
}

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'short',
  timeStyle: 'short',
});

function describeParams(entry: RecentCalculation): string {
  const pairs = Object.entries(entry.params);
  if (pairs.length === 0) {
    return 'default parameters';
  }
  return pairs.map(([key, value]) => `${key}=${value}`).join(', ');
}

/**
 * A per-browser convenience list (see `use-recent-calculations.ts`) of the
 * last several configurations run on this page, with one-click rerun —
 * useful for the common research pattern of comparing a small set of
 * configurations back and forth without re-filling every field each time.
 */
function RecentCalculationsPanelInner({ entries, onRerun }: RecentCalculationsPanelProps) {
  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 700, mb: 1 }}>
        Recent Calculations
      </Typography>
      {entries.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Calculations you run will appear here for quick rerun.
        </Typography>
      ) : (
        <List dense disablePadding aria-label="Recent calculations">
          {entries.map((entry) => (
            <ListItem
              key={`${entry.symbol}-${entry.indicator}-${entry.timeframe}-${entry.timestamp}`}
              disablePadding
              secondaryAction={
                <IconButton
                  size="small"
                  edge="end"
                  aria-label={`Rerun ${entry.indicatorLabel} on ${entry.symbol}`}
                  onClick={() => onRerun(entry)}
                >
                  <ReplayIcon fontSize="small" />
                </IconButton>
              }
            >
              <ListItemButton onClick={() => onRerun(entry)} sx={{ pr: 6 }}>
                <ListItemText
                  primary={`${entry.indicatorLabel} · ${entry.symbol} · ${entry.timeframe}`}
                  secondary={`${describeParams(entry)} — ${timeFormatter.format(entry.timestamp)}`}
                  slotProps={{
                    primary: { variant: 'body2', sx: { fontWeight: 600 } },
                    secondary: { variant: 'caption' },
                  }}
                />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      )}
    </Paper>
  );
}

export const RecentCalculationsPanel = memo(RecentCalculationsPanelInner);
