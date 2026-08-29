'use client';

import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import type { ExperimentSummary } from '@/types/api/experiments';

export interface BenchmarkFiltersValue {
  datasetVersion: string;
  targetColumn: string;
  experimentIds: string[];
}

export interface BenchmarkFiltersBarProps {
  value: BenchmarkFiltersValue;
  onChange: (next: BenchmarkFiltersValue) => void;
  onSubmit: () => void;
  experiments: ExperimentSummary[];
  experimentsLoading: boolean;
  datasetVersionOptions: string[];
  submitting: boolean;
}

/**
 * What to compare: at least one of dataset_version, target_column, or a
 * chosen set of experiments must be given — the same "at least one target"
 * requirement `POST /evaluation/benchmark` itself enforces
 * (`no_benchmark_target`). `experiment_ids`, when chosen, narrows an
 * already-matching set further rather than replacing it, so all three
 * fields stay usable together.
 */
export function BenchmarkFiltersBar({
  value,
  onChange,
  onSubmit,
  experiments,
  experimentsLoading,
  datasetVersionOptions,
  submitting,
}: BenchmarkFiltersBarProps) {
  const selectedExperiments = experiments.filter((e) => value.experimentIds.includes(e.id));
  const canSubmit = Boolean(
    value.datasetVersion.trim() || value.targetColumn.trim() || value.experimentIds.length > 0,
  );

  return (
    <Stack
      direction="row"
      spacing={1.5}
      flexWrap="wrap"
      useFlexGap
      alignItems="flex-start"
      component="form"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      <Autocomplete
        freeSolo
        options={datasetVersionOptions}
        inputValue={value.datasetVersion}
        onInputChange={(_, next) => onChange({ ...value, datasetVersion: next })}
        sx={{ minWidth: 220 }}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Dataset version"
            helperText="Only compare jobs trained over this dataset citation"
          />
        )}
      />
      <TextField
        label="Target column"
        value={value.targetColumn}
        onChange={(event) => onChange({ ...value, targetColumn: event.target.value })}
        helperText="e.g. next_direction, next_close"
        sx={{ minWidth: 200 }}
      />
      <Autocomplete
        multiple
        options={experiments}
        value={selectedExperiments}
        loading={experimentsLoading}
        getOptionLabel={(option) => option.name}
        isOptionEqualToValue={(option, option2) => option.id === option2.id}
        onChange={(_, next) => onChange({ ...value, experimentIds: next.map((e) => e.id) })}
        sx={{ minWidth: 260, flexGrow: 1 }}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Experiments"
            helperText="Optional — narrows the match further"
          />
        )}
      />
      <Button
        type="submit"
        variant="contained"
        startIcon={<CompareArrowsIcon />}
        disabled={!canSubmit || submitting}
        sx={{ height: 56 }}
      >
        Compare
      </Button>
    </Stack>
  );
}
