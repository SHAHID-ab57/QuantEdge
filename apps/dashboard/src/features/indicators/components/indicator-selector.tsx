'use client';

import Autocomplete from '@mui/material/Autocomplete';
import Chip from '@mui/material/Chip';
import ListItem from '@mui/material/ListItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { Indicator } from '@/types/api/indicators';

export interface IndicatorSelectorProps {
  indicators: Indicator[];
  value: string | null;
  onChange: (name: string) => void;
  loading?: boolean;
  disabled?: boolean;
}

/**
 * Picks one indicator from the catalogue. Grouped by the backend-declared
 * `category` so the list stays navigable as the registry grows toward the
 * hundreds of indicators this engine is built for — no category list is
 * hardcoded here.
 */
export function IndicatorSelector({
  indicators,
  value,
  onChange,
  loading = false,
  disabled = false,
}: IndicatorSelectorProps) {
  const selected = indicators.find((indicator) => indicator.name === value) ?? null;

  return (
    <Autocomplete
      value={selected}
      onChange={(_, option) => onChange(option?.name ?? '')}
      options={[...indicators].sort((a, b) => a.category.localeCompare(b.category))}
      groupBy={(option) => option.category}
      getOptionLabel={(option) => option.label}
      isOptionEqualToValue={(option, candidate) => option.name === candidate.name}
      loading={loading}
      disabled={disabled}
      size="small"
      sx={{ minWidth: 260, maxWidth: 360 }}
      renderOption={(props, option) => {
        const { key, ...rest } = props as typeof props & { key: string };
        return (
          <ListItem key={key} {...rest} sx={{ display: 'block' }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">{option.label}</Typography>
              <Chip label={option.name} size="small" variant="outlined" />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {option.description}
            </Typography>
          </ListItem>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label="Indicator"
          placeholder="e.g. Simple Moving Average"
          inputProps={{ ...params.inputProps, 'aria-label': 'Select an indicator' }}
        />
      )}
    />
  );
}
