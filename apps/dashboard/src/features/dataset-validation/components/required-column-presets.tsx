'use client';

import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { COLUMN_PRESETS, type ColumnPresetKey } from '../lib/resolve-required-columns';

export interface RequiredColumnPresetsProps {
  onApply: (key: ColumnPresetKey) => void;
  disabled?: boolean;
}

/**
 * One-click starting points for both the feature selection and the
 * Required Columns list — applying a preset seeds both from the live
 * catalogue (never a hardcoded feature list) and a researcher can still
 * add, remove, or customize anything afterward; a preset is a starting
 * point, not a locked configuration.
 */
export function RequiredColumnPresets({ onApply, disabled = false }: RequiredColumnPresetsProps) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" color="text.secondary">
        Presets
      </Typography>
      <Stack
        direction="row"
        spacing={0.5}
        flexWrap="wrap"
        useFlexGap
        role="group"
        aria-label="Required column presets"
      >
        {COLUMN_PRESETS.map((preset) => (
          <Chip
            key={preset.key}
            size="small"
            variant="outlined"
            label={preset.label}
            title={preset.description}
            onClick={() => onApply(preset.key)}
            disabled={disabled}
            aria-label={`Apply ${preset.label} preset`}
          />
        ))}
      </Stack>
    </Stack>
  );
}
