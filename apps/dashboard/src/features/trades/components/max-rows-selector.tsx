'use client';

import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';

export const MAX_ROWS_OPTIONS = [25, 50, 100, 200] as const;
export type MaxRowsOption = (typeof MAX_ROWS_OPTIONS)[number];
export const DEFAULT_MAX_ROWS: MaxRowsOption = 100;

export interface MaxRowsSelectorProps {
  value: MaxRowsOption;
  onChange: (maxRows: MaxRowsOption) => void;
}

/**
 * Configurable trade-tape row cap. Same `ToggleButtonGroup` interaction
 * pattern as the Order Book's `DepthSelector` (itself matching the chart
 * module's `TimeframeSelector`) — not extracted into one shared generic
 * component since each domain (timeframes, depth levels, tape rows) has
 * its own fixed option set and default.
 */
export function MaxRowsSelector({ value, onChange }: MaxRowsSelectorProps) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, next: MaxRowsOption | null) => {
        if (next !== null) {
          onChange(next);
        }
      }}
      aria-label="Select the maximum number of trade tape rows"
    >
      {MAX_ROWS_OPTIONS.map((rows) => (
        <ToggleButton key={rows} value={rows} aria-label={`${rows} rows`}>
          {rows}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
