'use client';

import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';

export interface TimeframeSelectorProps {
  timeframes: string[];
  value: string | null;
  onChange: (timeframe: string) => void;
  size?: 'small' | 'medium';
}

/**
 * Generic timeframe picker driven entirely by the `timeframes` prop (in
 * practice, whatever `GET /api/v1/markets/{symbol}/timeframes` returns for
 * the selected market — e.g. `1m`, `5m`, `15m`, `1h`, `4h`, `1d`). A
 * `ToggleButtonGroup` gives native keyboard (arrow-key) navigation between
 * options, satisfying Objective #12's accessibility requirement without
 * extra wiring.
 *
 * Standalone/reusable, like `MarketSelector` — see FRONTEND.md for why the
 * History page integration reuses its own timeframe control instead.
 */
export function TimeframeSelector({
  timeframes,
  value,
  onChange,
  size = 'small',
}: TimeframeSelectorProps) {
  return (
    <ToggleButtonGroup
      value={value}
      exclusive
      size={size}
      onChange={(_, next: string | null) => {
        if (next) {
          onChange(next);
        }
      }}
      aria-label="Select a timeframe for the chart"
    >
      {timeframes.map((timeframe) => (
        <ToggleButton key={timeframe} value={timeframe} aria-label={timeframe}>
          {timeframe}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
