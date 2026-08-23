'use client';

import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

/**
 * A label + big value tile — the "one stat" building block that kept
 * getting reinvented locally (the Live Market price card's `Stat`, the
 * Order Book's spread panel's `Stat`) each time a page needed a small grid
 * of numbers. Pulled out here once a third page (Live Trade Analytics)
 * needed the exact same shape, rather than writing a fourth local copy.
 *
 * Deliberately does *not* try to also cover `ConnectionStatus`'s
 * `StatusItem` — that one has a colored status dot and `dt`/`dd` semantics
 * for a genuinely different concept (component health), not a number to
 * read.
 */
export interface StatTileProps {
  label: string;
  value: ReactNode;
  /** MUI color token or CSS color, e.g. `'success.main'`. Defaults to the theme's primary text color. */
  color?: string;
  /** Tooltip shown on hover, for a figure that needs a one-line explanation. */
  hint?: string;
  /** Secondary line under the value, e.g. a relative timestamp. */
  caption?: string;
  /** Larger type for the single most important figure on a page (e.g. current price). */
  emphasis?: boolean;
  /** Centers the label/value/caption — used where tiles sit in a horizontally centered row. */
  align?: 'left' | 'center';
  /**
   * Rendered immediately after the label — the Trade Analytics dashboard
   * passes its `MetricInfo` button here. Kept as a generic slot rather than
   * a metric-key prop so this shared component takes no dependency on that
   * feature's help dictionary.
   */
  adornment?: ReactNode;
  /** Overrides the tile's minimum width; the default suits a 3–4 word label. */
  minWidth?: number;
}

/** Matches the Live Market/Order Book convention: a value equal to this renders as disabled/muted text. */
const UNAVAILABLE = 'Unavailable';

export function StatTile({
  label,
  value,
  color,
  hint,
  caption,
  emphasis = false,
  align = 'left',
  adornment,
  minWidth = 120,
}: StatTileProps) {
  const isUnavailable = value === UNAVAILABLE;
  const body = (
    <Stack
      spacing={0.25}
      alignItems={align === 'center' ? 'center' : 'flex-start'}
      sx={{ minWidth }}
    >
      <Stack
        direction="row"
        spacing={0.25}
        alignItems="center"
        justifyContent={align === 'center' ? 'center' : 'flex-start'}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ letterSpacing: 0.2, whiteSpace: 'nowrap' }}
        >
          {label}
        </Typography>
        {adornment}
      </Stack>
      <Typography
        variant={emphasis ? 'h5' : 'h6'}
        component="p"
        sx={{
          fontWeight: 600,
          color: color ?? (isUnavailable ? 'text.disabled' : 'text.primary'),
          fontVariantNumeric: 'tabular-nums',
          fontSize: emphasis ? '1.5rem' : '1.125rem',
          lineHeight: 1.25,
          // A muted "Unavailable" placeholder should not shout as loudly as a
          // real figure — it is the absence of data, not a data point.
          ...(isUnavailable && { fontSize: emphasis ? '1.125rem' : '0.9375rem', fontWeight: 500 }),
        }}
      >
        {value}
      </Typography>
      {caption ? (
        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
          {caption}
        </Typography>
      ) : null}
    </Stack>
  );
  return hint ? <Tooltip title={hint}>{body}</Tooltip> : body;
}
