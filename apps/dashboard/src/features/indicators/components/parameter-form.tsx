'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import type { IndicatorParameterSpec } from '@/types/api/indicators';
import type { ParameterKnowledge } from '../lib/indicator-knowledge';
import type { ParameterValues } from '../lib/parameter-values';

export interface ParameterFormProps {
  specs: readonly IndicatorParameterSpec[];
  values: ParameterValues;
  errors: Record<string, string>;
  disabled?: boolean;
  onChange: (name: string, value: string) => void;
  /** Curated per-parameter hints/recommended values, keyed by parameter name — see `indicator-knowledge.ts`. */
  parameterKnowledge?: Record<string, ParameterKnowledge>;
}

/**
 * Renders an indicator's parameter inputs **entirely from the backend's
 * published specs** — the field type, bounds, choices, help text, and
 * required-ness all come from `IndicatorParameterSpec`.
 *
 * Nothing here knows that SMA has a `period` or that RSI is bounded at 2.
 * That is the whole point: a new indicator registered on the backend gets
 * a correct, constrained form on this page with no frontend change, which
 * is the frontend half of the "add an indicator without touching the
 * engine" guarantee. `parameterKnowledge` is a purely additive enrichment
 * layer on top of that — a richer tooltip and a row of common-value chips
 * when curated content exists for the parameter, falling back to just the
 * spec's own description when it doesn't, so an uncurated indicator's form
 * is still fully correct and usable.
 */
function ParameterFormInner({
  specs,
  values,
  errors,
  disabled = false,
  onChange,
  parameterKnowledge = {},
}: ParameterFormProps) {
  if (specs.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        This indicator takes no parameters.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'flex-start' }}>
      {specs.map((spec) => {
        const value = values[spec.name] ?? '';
        const error = errors[spec.name];
        const helperText = error ?? spec.description;
        const isChoice = spec.choices.length > 0;
        const knowledge = parameterKnowledge[spec.name];
        const recommended = knowledge?.recommended ?? [];

        return (
          <Box key={spec.name} sx={{ minWidth: 200, maxWidth: 280 }}>
            <Stack direction="row" spacing={0.25} alignItems="flex-start">
              <TextField
                select={isChoice}
                type={isChoice ? undefined : numericInputType(spec)}
                size="small"
                label={spec.label}
                value={value}
                disabled={disabled}
                required={spec.required}
                error={Boolean(error)}
                helperText={helperText}
                onChange={(event) => onChange(spec.name, event.target.value)}
                slotProps={{
                  htmlInput: isChoice
                    ? undefined
                    : {
                        'aria-label': spec.label,
                        ...(spec.minimum !== null ? { min: spec.minimum } : {}),
                        ...(spec.maximum !== null ? { max: spec.maximum } : {}),
                        ...(spec.type === 'float' ? { step: 'any' } : {}),
                      },
                }}
                sx={{ flex: 1, minWidth: 0 }}
              >
                {spec.choices.map((choice) => (
                  <MenuItem key={choice} value={choice}>
                    {choice}
                  </MenuItem>
                ))}
              </TextField>
              <Box sx={{ mt: 1 }}>
                <InfoTooltip
                  label={spec.label}
                  sections={[
                    { heading: 'What it means', body: knowledge?.hint ?? spec.description },
                  ]}
                />
              </Box>
            </Stack>
            {recommended.length > 0 ? (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ alignSelf: 'center', mr: 0.25 }}
                >
                  Recommended:
                </Typography>
                {recommended.map((option) => (
                  <Chip
                    key={String(option)}
                    label={option}
                    size="small"
                    variant={value === String(option) ? 'filled' : 'outlined'}
                    color={value === String(option) ? 'primary' : 'default'}
                    onClick={() => onChange(spec.name, String(option))}
                    disabled={disabled}
                  />
                ))}
              </Stack>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

/** Map a declared parameter type onto the right HTML input type. */
function numericInputType(spec: IndicatorParameterSpec): string {
  return spec.type === 'int' || spec.type === 'float' ? 'number' : 'text';
}

export const ParameterForm = memo(ParameterFormInner);
