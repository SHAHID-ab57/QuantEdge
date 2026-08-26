'use client';

import BarChartIcon from '@mui/icons-material/BarChart';
import IconButton from '@mui/material/IconButton';
import Popover from '@mui/material/Popover';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState, type MouseEvent } from 'react';
import type { FeatureCell } from '@/types/api/features';
import { computeColumnStats } from '../lib/column-stats';

export interface ColumnStatsPopoverProps {
  columnName: string;
  values: readonly FeatureCell[];
  /**
   * Whether `values` is only the rendered/preview subset rather than the
   * full dataset — shown as a caveat so a statistic is never mistaken for
   * a full-dataset figure when the table is capped.
   */
  isPreviewSubset: boolean;
}

function StatRow({ label, value }: { label: string; value: number | null }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {value === null ? '—' : Number(value.toPrecision(6)).toString()}
      </Typography>
    </Stack>
  );
}

/**
 * A click-to-open popover of a numeric column's min/max/mean/std/null
 * count, anchored to a small icon button beside the column header.
 * Statistics are computed lazily (only while the popover is open) over
 * whatever rows are currently passed in — the caller decides whether that
 * is the full dataset or only the rendered preview window, and
 * `isPreviewSubset` makes that scope explicit in the popover itself.
 */
export function ColumnStatsPopover({
  columnName,
  values,
  isPreviewSubset,
}: ColumnStatsPopoverProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);

  const handleOpen = (event: MouseEvent<HTMLElement>) => {
    event.stopPropagation();
    setAnchor(event.currentTarget);
  };
  const handleClose = () => setAnchor(null);

  const stats = open ? computeColumnStats(values) : null;

  return (
    <>
      <IconButton
        size="small"
        aria-label={`Show statistics for ${columnName}`}
        onClick={handleOpen}
        sx={{ p: 0.25 }}
      >
        <BarChartIcon sx={{ fontSize: 14 }} />
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={handleClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Stack spacing={0.5} sx={{ p: 1.5, minWidth: 190 }}>
          <Typography variant="subtitle2">{columnName}</Typography>
          {stats ? (
            <>
              <StatRow label="Min" value={stats.min} />
              <StatRow label="Max" value={stats.max} />
              <StatRow label="Mean" value={stats.mean} />
              <StatRow label="Std Dev" value={stats.std} />
              <StatRow label="Null count" value={stats.nullCount} />
              {isPreviewSubset ? (
                <Typography variant="caption" color="text.secondary" sx={{ pt: 0.5 }}>
                  Computed over the rendered preview rows only.
                </Typography>
              ) : null}
            </>
          ) : null}
        </Stack>
      </Popover>
    </>
  );
}
