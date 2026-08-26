'use client';

import CloseIcon from '@mui/icons-material/Close';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { ParameterForm } from '@/features/indicators/components/parameter-form';
import { validateValues } from '@/features/indicators/lib/parameter-values';
import type { TargetDTO } from '@/types/api/ml-datasets';
import { HorizonPresetSelect } from './horizon-preset-select';
import { horizonSpecFor } from '../lib/horizon-presets';
import { horizonRangeText, targetProblemTypeLabel } from '../lib/target-type';
import { isTargetSelected, type TargetSelection } from '../lib/target-selection';

export interface TargetSelectorProps {
  targets: TargetDTO[];
  loading?: boolean;
  selections: TargetSelection[];
  onToggle: (target: TargetDTO) => void;
  onParamsChange: (target: string, params: Record<string, string>) => void;
}

const PROBLEM_TYPE_COLOR: Record<string, 'secondary' | 'primary'> = {
  Classification: 'secondary',
  Regression: 'primary',
};

/** One option row in the target-search dropdown: name, problem type, description, output, horizon range. */
function TargetOption({ target }: { target: TargetDTO }) {
  const problemType = targetProblemTypeLabel(target);
  return (
    <Stack spacing={0.25} sx={{ py: 0.25 }}>
      <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {target.label}
        </Typography>
        <Chip size="small" color={PROBLEM_TYPE_COLOR[problemType]} label={problemType} />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        {target.description}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Output: {target.outputs.join(', ') || 'Not documented'} · {horizonRangeText(target)}
      </Typography>
    </Stack>
  );
}

interface SelectedTargetCardProps {
  target: TargetDTO;
  selection: TargetSelection;
  onRemove: () => void;
  onParamsChange: (target: string, params: Record<string, string>) => void;
}

/**
 * One selected target's editable configuration: its output columns, its
 * `horizon` parameter via the preset dropdown (`HorizonPresetSelect`), any
 * *other* declared parameter via the generic `ParameterForm` (no builtin
 * target has one today, but a future target might), and a remove action.
 */
function SelectedTargetCard({
  target,
  selection,
  onRemove,
  onParamsChange,
}: SelectedTargetCardProps) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const horizonSpec = horizonSpecFor(target.parameters);
  const otherSpecs = target.parameters.filter((parameter) => parameter.name !== 'horizon');
  const problemType = targetProblemTypeLabel(target);

  const commitIfValid = (next: Record<string, string>) => {
    const found = validateValues(target.parameters, next);
    setErrors(found);
    // Commit only a fully-valid parameter set — the same discipline
    // `FeatureSelector` uses, so a request is never sent with a horizon
    // value the backend is guaranteed to reject.
    if (Object.keys(found).length === 0) {
      onParamsChange(target.name, next);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 1.25 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="space-between">
          <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {target.label}
            </Typography>
            <Chip size="small" color={PROBLEM_TYPE_COLOR[problemType]} label={problemType} />
            <InfoTooltip
              label={target.label}
              sections={[
                { heading: 'Purpose', body: target.description },
                { heading: 'Output columns', body: target.outputs.join(', ') || 'Not documented.' },
                { heading: 'Horizon compatibility', body: horizonRangeText(target) },
                { heading: 'Version', body: `${target.version} · ${target.author}` },
              ]}
            />
          </Stack>
          <IconButton size="small" aria-label={`Remove ${target.label}`} onClick={onRemove}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>

        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {target.outputs.map((output) => (
            <Chip key={output} size="small" variant="outlined" label={output} />
          ))}
        </Stack>

        {horizonSpec ? (
          <HorizonPresetSelect
            spec={horizonSpec}
            value={selection.params.horizon ?? String(target.default_horizon)}
            error={errors.horizon}
            onChange={(value) => commitIfValid({ ...selection.params, horizon: value })}
          />
        ) : null}

        {otherSpecs.length > 0 ? (
          <ParameterForm
            specs={otherSpecs}
            values={selection.params}
            errors={errors}
            onChange={(name, value) => commitIfValid({ ...selection.params, [name]: value })}
          />
        ) : null}
      </Stack>
    </Paper>
  );
}

function SelectorSkeleton() {
  return (
    <Stack spacing={1} role="status" aria-label="Loading target catalogue">
      {[0, 1, 2].map((key) => (
        <Skeleton key={key} variant="rounded" height={36} />
      ))}
    </Stack>
  );
}

/**
 * Which prediction targets to append to the dataset as label columns.
 *
 * A searchable multi-select (`Autocomplete`, the same widget
 * `RequiredColumnsSelector` uses in the Dataset Validation module) replaces
 * a fixed checkbox list, since the target catalogue is expected to grow —
 * a search box scales to a much larger catalogue than a flat list does.
 * Each selected target then gets its own configuration card below, since a
 * dropdown option row has no room for a live parameter form.
 */
export function TargetSelector({
  targets,
  loading = false,
  selections,
  onToggle,
  onParamsChange,
}: TargetSelectorProps) {
  if (loading) {
    return <SelectorSkeleton />;
  }

  if (targets.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No target generators are registered.
      </Typography>
    );
  }

  const selectedTargets = selections
    .map((selection) => targets.find((target) => target.name === selection.target))
    .filter((target): target is TargetDTO => target !== undefined);

  const handleAutocompleteChange = (nextSelected: TargetDTO[]) => {
    // Diff against the current selection and toggle only what changed —
    // preserves every other selection's already-configured params and
    // reuses the exact same add/remove semantics `onToggle` already gives
    // the checkbox-list rows on the Feature Selector.
    const nextNames = new Set(nextSelected.map((target) => target.name));
    for (const target of selectedTargets) {
      if (!nextNames.has(target.name)) {
        onToggle(target);
      }
    }
    for (const target of nextSelected) {
      if (!isTargetSelected(selections, target.name)) {
        onToggle(target);
      }
    }
  };

  return (
    <Stack spacing={1.5} aria-label="Available prediction targets">
      <Autocomplete
        multiple
        options={targets}
        value={selectedTargets}
        onChange={(_, next) => handleAutocompleteChange(next)}
        getOptionLabel={(target) => target.label}
        isOptionEqualToValue={(option, value) => option.name === value.name}
        renderOption={(props, target) => (
          <Box component="li" {...props} key={target.name}>
            <TargetOption target={target} />
          </Box>
        )}
        renderTags={(value, getTagProps) =>
          value.map((target, index) => (
            <Chip size="small" label={target.label} {...getTagProps({ index })} key={target.name} />
          ))
        }
        renderInput={(params) => (
          <TextField
            {...params}
            label="Prediction targets"
            placeholder="Search targets…"
            slotProps={{
              htmlInput: { ...params.inputProps, 'aria-label': 'Search prediction targets' },
            }}
          />
        )}
      />

      <Stack spacing={1}>
        {selections.map((selection) => {
          const target = targets.find((entry) => entry.name === selection.target);
          if (!target) {
            return null;
          }
          return (
            <SelectedTargetCard
              key={target.name}
              target={target}
              selection={selection}
              onRemove={() => onToggle(target)}
              onParamsChange={onParamsChange}
            />
          );
        })}
      </Stack>
    </Stack>
  );
}

export { isTargetSelected };
