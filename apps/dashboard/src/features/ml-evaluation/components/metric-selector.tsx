'use client';

import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';

export interface MetricSelectorProps {
  metricNames: string[];
  value: string | null;
  onChange: (metric: string | null) => void;
}

/**
 * Which metric ranks the comparison table and drives its "Rank" column —
 * any metric present on at least one matched candidate, not a fixed list.
 * Selecting "None" falls back to the table's default `completed_at`
 * ordering (Benchmark History's own view).
 */
export function MetricSelector({ metricNames, value, onChange }: MetricSelectorProps) {
  return (
    <FormControl size="small" sx={{ minWidth: 200 }}>
      <InputLabel id="metric-selector-label">Rank by metric</InputLabel>
      <Select
        labelId="metric-selector-label"
        label="Rank by metric"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <MenuItem value="">
          <em>None (most recent first)</em>
        </MenuItem>
        {metricNames.map((name) => (
          <MenuItem key={name} value={name}>
            {name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
