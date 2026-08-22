'use client';

import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { DEPTH_OPTIONS, type DepthOption } from '../lib/order-book-depth';

export interface DepthSelectorProps {
  value: DepthOption;
  onChange: (depth: DepthOption) => void;
}

/**
 * Same `ToggleButtonGroup` interaction pattern as the chart module's
 * `TimeframeSelector` (native keyboard navigation between options), applied
 * to a different, numeric domain — not extracted into a shared generic
 * component since the two aren't actually interchangeable (string
 * timeframes vs. fixed depth levels with a distinct default).
 */
export function DepthSelector({ value, onChange }: DepthSelectorProps) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size="small"
      onChange={(_, next: DepthOption | null) => {
        if (next !== null) {
          onChange(next);
        }
      }}
      aria-label="Select the number of order book levels to display"
    >
      {DEPTH_OPTIONS.map((depth) => (
        <ToggleButton key={depth} value={depth} aria-label={`${depth} levels`}>
          {depth}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
