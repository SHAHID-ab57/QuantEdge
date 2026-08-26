'use client';

import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMemo, useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import type { IndicatorParameterSpec } from '@/types/api/indicators';
import { CUSTOM_HORIZON_VALUE, isPresetValue, presetsInRange } from '../lib/horizon-presets';

export interface HorizonPresetSelectProps {
  spec: IndicatorParameterSpec;
  /** The horizon value as a string, matching the rest of this app's parameter-form convention. */
  value: string;
  error?: string;
  onChange: (value: string) => void;
}

const HORIZON_TOOLTIP = [
  {
    heading: 'Prediction Horizon',
    body: 'Prediction horizon represents how many future candles ahead the target is generated.',
  },
];

/**
 * A prediction-target's `horizon` parameter, presented as a searchable
 * preset dropdown (1/2/3/5/10/20/50 candles) with a "Custom…" escape
 * hatch — replacing a bare numeric field, which gives a researcher no
 * sense of what a "typical" horizon looks like.
 *
 * This is a **display-only** specialization: the underlying value is
 * still a plain string committed through the same `onChange` callback
 * every other parameter field uses, and still validated by the caller
 * against this exact same `spec` (`validateValues` from
 * `indicators/lib/parameter-values.ts`) before being accepted — the preset
 * dropdown does not introduce a second validation path.
 */
export function HorizonPresetSelect({ spec, value, error, onChange }: HorizonPresetSelectProps) {
  const presets = useMemo(() => presetsInRange(spec.minimum, spec.maximum), [spec]);
  // Whether "Custom…" was explicitly chosen — kept as its own bit of state
  // rather than derived solely from `value`, since a value that already
  // happens to be a preset (e.g. the initial default) must still be able
  // to switch into "Custom…" mode without the field silently reverting.
  const [forceCustom, setForceCustom] = useState(false);
  const showCustomField = forceCustom || !isPresetValue(value, presets);
  const selectValue = showCustomField ? CUSTOM_HORIZON_VALUE : value;

  const handleSelectChange = (next: string) => {
    if (next === CUSTOM_HORIZON_VALUE) {
      // Reveal the custom field without discarding whatever the current
      // value already is — it may already be a valid, just non-preset, number.
      setForceCustom(true);
      return;
    }
    setForceCustom(false);
    onChange(next);
  };

  return (
    <Stack direction="row" spacing={0.5} alignItems="flex-start">
      <TextField
        select
        size="small"
        label="Horizon"
        value={selectValue}
        onChange={(event) => handleSelectChange(event.target.value)}
        slotProps={{ select: { 'aria-label': 'Prediction horizon' } }}
        sx={{ minWidth: 150 }}
      >
        {presets.map((preset) => (
          <MenuItem key={preset} value={String(preset)}>
            {preset} candle{preset === 1 ? '' : 's'}
          </MenuItem>
        ))}
        <MenuItem value={CUSTOM_HORIZON_VALUE}>Custom…</MenuItem>
      </TextField>
      {showCustomField ? (
        <TextField
          size="small"
          type="number"
          label="Custom horizon"
          value={value}
          error={Boolean(error)}
          helperText={error}
          onChange={(event) => onChange(event.target.value)}
          slotProps={{
            htmlInput: {
              'aria-label': 'Custom prediction horizon',
              min: spec.minimum ?? undefined,
              max: spec.maximum ?? undefined,
            },
          }}
          sx={{ width: 150 }}
        />
      ) : null}
      <InfoTooltip label="Prediction Horizon" sections={HORIZON_TOOLTIP} />
    </Stack>
  );
}
