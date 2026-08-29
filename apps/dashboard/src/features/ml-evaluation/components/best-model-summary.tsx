'use client';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { BenchmarkBestEntry } from '@/types/api/evaluation';

export interface BestModelSummaryProps {
  bestByMetric: BenchmarkBestEntry[];
}

/**
 * One card per metric: which model won it, and its value — the direct
 * answer to "which model performs best" the Manager's Note asked this
 * milestone to unblock. `higher_is_better` (per metric, from the registry)
 * decides the arrow direction shown, never a hardcoded assumption.
 */
export function BestModelSummary({ bestByMetric }: BestModelSummaryProps) {
  if (bestByMetric.length === 0) return null;

  return (
    <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
      {bestByMetric.map((entry) => (
        <Paper
          key={entry.metric}
          variant="outlined"
          sx={{ p: 1.5, minWidth: 160, borderColor: 'divider' }}
        >
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <EmojiEventsIcon fontSize="small" color="warning" />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ textTransform: 'uppercase' }}
              >
                {entry.metric}
              </Typography>
              {entry.higher_is_better ? (
                <ArrowUpwardIcon fontSize="inherit" color="success" />
              ) : (
                <ArrowDownwardIcon fontSize="inherit" color="success" />
              )}
            </Stack>
            <Chip size="small" label={entry.model_type} />
            <Typography variant="h6">{entry.value.toFixed(4)}</Typography>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
