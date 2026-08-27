'use client';

import ScienceIcon from '@mui/icons-material/Science';
import DatasetIcon from '@mui/icons-material/Dataset';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { InfoTooltip } from '@/components/info-tooltip';
import { useExperiment } from '@/features/experiments/hooks/use-experiments-data';
import { fetchExperiments } from '@/lib/api/experiments';
import { fetchMarkets, fetchTimeframes } from '@/lib/api/market';
import type { ExperimentSummary } from '@/types/api/experiments';
import type { ModelAdapter } from '@/types/api/training';
import { useModelAdapters, useCreateTrainingJob } from '../hooks/use-training-jobs-data';
import {
  DATASET_VERSION_FIELD_HELP,
  EXPERIMENT_FIELD_HELP,
  MODEL_TYPE_FIELD_HELP,
  SYMBOL_FIELD_HELP,
  TARGET_COLUMN_FIELD_HELP,
  TIMEFRAME_FIELD_HELP,
} from '../lib/training-job-help';
import { EmptyStateNotice } from './empty-state-notice';
import {
  HyperparameterEditor,
  buildHyperparametersPayload,
  defaultKnownHyperparameterValues,
  knownHyperparametersAreValid,
  type HyperparameterEntry,
} from './hyperparameter-editor';
import { TrainingSummaryPanel } from './training-summary-panel';

const EMPTY_EXPERIMENT_OPTIONS: ExperimentSummary[] = [];

export interface CreateTrainingJobDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
  /** Pre-selects the experiment when opened from an experiment's own context. */
  defaultExperimentId?: string;
}

/**
 * Registers a new training job: which experiment it trains for (the
 * Experiment selector), which dataset it cites (the Dataset selector —
 * defaults from the selected experiment's own `dataset_version`, since the
 * ML Dataset Builder persists nothing to pick from independently; see
 * `app/training/base.py`'s `TrainingDataset` docstring), which registered
 * model adapter runs it, and its hyperparameters. Creating a job never
 * runs it — it starts `pending`; the list view's Run action executes the
 * pipeline.
 *
 * Selecting an experiment fetches its full record (`useExperiment`, the
 * same hook the Experiment detail page uses) so `TrainingSummaryPanel` can
 * show the experiment's own Target/Feature Set/Split Configuration as a
 * read-only preview — never editable here, since those describe what the
 * experiment's dataset was actually built with, not something a training
 * job gets to redefine.
 */
export function CreateTrainingJobDialog({
  open,
  onClose,
  onCreated,
  defaultExperimentId,
}: CreateTrainingJobDialogProps) {
  const create = useCreateTrainingJob();
  const modelAdapters = useModelAdapters();
  const experiments = useQuery({
    queryKey: ['experiments', 'select-options'],
    queryFn: () => fetchExperiments({ limit: 200, sort: 'updated_at', dir: 'desc' }),
    enabled: open,
  });

  const [experiment, setExperiment] = useState<ExperimentSummary | null>(null);
  const [datasetVersion, setDatasetVersion] = useState('');
  const [datasetVersionTouched, setDatasetVersionTouched] = useState(false);
  const [modelType, setModelType] = useState('');
  const [symbol, setSymbol] = useState('');
  const [timeframe, setTimeframe] = useState('');
  const [targetColumn, setTargetColumn] = useState('');
  const [knownValues, setKnownValues] = useState<Record<string, string>>(() =>
    defaultKnownHyperparameterValues(),
  );
  const [customEntries, setCustomEntries] = useState<HyperparameterEntry[]>([]);

  const markets = useQuery({
    queryKey: ['markets', 'select-options'],
    queryFn: () => fetchMarkets(),
    enabled: open,
  });
  const timeframes = useQuery({
    queryKey: ['timeframes', symbol],
    queryFn: () => fetchTimeframes(symbol),
    enabled: open && symbol.length > 0,
  });

  const experimentOptions = useMemo(
    () => experiments.data?.experiments ?? EMPTY_EXPERIMENT_OPTIONS,
    [experiments.data],
  );
  const experimentDetail = useExperiment(experiment?.id ?? '');

  const datasetVersionOptions = useMemo(
    () =>
      Array.from(
        new Set(
          experimentOptions
            .map((option) => option.dataset_version)
            .filter((value): value is string => Boolean(value)),
        ),
      ),
    [experimentOptions],
  );

  useEffect(() => {
    if (!open) return;
    if (!defaultExperimentId || experimentOptions.length === 0) return;
    const match = experimentOptions.find((option) => option.id === defaultExperimentId);
    if (match) {
      setExperiment(match);
      setDatasetVersion(match.dataset_version ?? '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once options arrive, not per-render
  }, [open, defaultExperimentId, experimentOptions.length]);

  useEffect(() => {
    if (open && modelAdapters.data && modelType === '' && modelAdapters.data.adapters.length > 0) {
      setModelType(modelAdapters.data.adapters[0]?.name ?? '');
    }
  }, [open, modelAdapters.data, modelType]);

  const selectedAdapter = useMemo(
    () => modelAdapters.data?.adapters.find((adapter) => adapter.name === modelType),
    [modelAdapters.data, modelType],
  );

  const reset = () => {
    setExperiment(null);
    setDatasetVersion('');
    setDatasetVersionTouched(false);
    setModelType('');
    setSymbol('');
    setTimeframe('');
    setTargetColumn('');
    setKnownValues(defaultKnownHyperparameterValues());
    setCustomEntries([]);
    create.reset();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleExperimentChange = (next: ExperimentSummary | null) => {
    setExperiment(next);
    // Only overwrite a dataset version the researcher hasn't already
    // hand-edited — switching experiments shouldn't silently discard an
    // intentional override.
    if (!datasetVersionTouched) {
      setDatasetVersion(next?.dataset_version ?? '');
    }
  };

  const hyperparametersValid = knownHyperparametersAreValid(knownValues);
  const requiresRealData = selectedAdapter?.requires_real_data ?? false;
  const validationReasons: string[] = [];
  if (!experiment) validationReasons.push('Select an experiment.');
  if (!datasetVersion.trim()) validationReasons.push('Enter or select a dataset version.');
  if (!modelType) validationReasons.push('Select a model type.');
  if (requiresRealData && !symbol) validationReasons.push('Select a market symbol.');
  if (requiresRealData && !timeframe) validationReasons.push('Select a timeframe.');
  if (!hyperparametersValid) validationReasons.push('Fix the invalid hyperparameter values below.');

  const handleSubmit = async () => {
    if (!experiment || validationReasons.length > 0) return;
    const created = await create.mutateAsync({
      experiment_id: experiment.id,
      model_type: modelType,
      dataset_version: datasetVersion.trim() || null,
      symbol: symbol || null,
      timeframe: timeframe || null,
      target_column: targetColumn.trim() || null,
      hyperparameters: buildHyperparametersPayload(knownValues, customEntries),
    });
    reset();
    onCreated(created.id);
  };

  const canSubmit = validationReasons.length === 0 && !create.isPending;
  const noExperiments = !experiments.isLoading && experimentOptions.length === 0;
  const noModelAdapters =
    !modelAdapters.isLoading && (modelAdapters.data?.adapters.length ?? 0) === 0;
  const noDatasetCitations =
    !experiments.isLoading && datasetVersionOptions.length === 0 && !datasetVersion;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Register a New Training Job</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {noExperiments ? (
            <EmptyStateNotice
              icon={<ScienceIcon fontSize="small" color="disabled" />}
              title="No experiments exist"
              description="A training job always trains for an existing experiment. Create one first."
              actionLabel="Create an Experiment"
              actionHref="/experiments"
            />
          ) : null}

          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <Autocomplete
              fullWidth
              options={experimentOptions}
              value={experiment}
              loading={experiments.isLoading}
              disabled={noExperiments}
              getOptionLabel={(option) => option.name}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              onChange={(_, next) => handleExperimentChange(next)}
              noOptionsText="No experiments match your search"
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Experiment"
                  required
                  helperText={
                    experiments.isLoading
                      ? 'Loading experiments…'
                      : 'The experiment this job trains for; its status and outcome update it.'
                  }
                  slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Experiment' } }}
                />
              )}
            />
            <InfoTooltip label="Experiment" sections={EXPERIMENT_FIELD_HELP} />
          </Stack>

          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <Autocomplete
              fullWidth
              freeSolo
              options={datasetVersionOptions}
              inputValue={datasetVersion}
              onInputChange={(_, next) => {
                setDatasetVersion(next);
                setDatasetVersionTouched(true);
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Dataset version"
                  required
                  helperText="Defaults from the selected experiment's dataset_version; search or type to override."
                  slotProps={{
                    htmlInput: { ...params.inputProps, 'aria-label': 'Dataset version' },
                  }}
                />
              )}
            />
            <InfoTooltip label="Dataset version" sections={DATASET_VERSION_FIELD_HELP} />
          </Stack>
          {noDatasetCitations ? (
            <EmptyStateNotice
              icon={<DatasetIcon fontSize="small" color="disabled" />}
              title="No datasets available"
              description="No experiment has a recorded dataset version yet. Build a dataset first, then record its id on an experiment."
              actionLabel="Build a dataset"
              actionHref="/ml-datasets"
            />
          ) : null}

          {noModelAdapters ? (
            <EmptyStateNotice
              icon={<SmartToyIcon fontSize="small" color="disabled" />}
              title="No model adapters registered"
              description="No model adapter is registered on the backend. Register a model adapter (app/training/adapters/) before creating a job."
            />
          ) : null}
          <Stack direction="row" spacing={0.5} alignItems="flex-start">
            <Autocomplete
              fullWidth
              disabled={noModelAdapters}
              options={modelAdapters.data?.adapters ?? []}
              loading={modelAdapters.isLoading}
              value={selectedAdapter ?? null}
              getOptionLabel={(option) => option.label}
              isOptionEqualToValue={(option, value) => option.name === value.name}
              onChange={(_, next: ModelAdapter | null) => setModelType(next?.name ?? '')}
              noOptionsText="No model adapters match your search"
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Model type"
                  required
                  helperText={
                    selectedAdapter?.description ??
                    'A registered model adapter — see the catalogue.'
                  }
                  slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Model type' } }}
                />
              )}
            />
            <InfoTooltip label="Model type" sections={MODEL_TYPE_FIELD_HELP} />
          </Stack>

          {requiresRealData ? (
            <Stack spacing={2}>
              <Typography variant="subtitle2">Configuration</Typography>
              <Stack direction="row" spacing={0.5} alignItems="flex-start">
                <Autocomplete
                  fullWidth
                  options={markets.data?.markets ?? []}
                  loading={markets.isLoading}
                  value={markets.data?.markets.find((m) => m.symbol === symbol) ?? null}
                  getOptionLabel={(option) => option.symbol}
                  isOptionEqualToValue={(option, value) => option.symbol === value.symbol}
                  onChange={(_, next) => {
                    setSymbol(next?.symbol ?? '');
                    setTimeframe('');
                  }}
                  noOptionsText="No markets match your search"
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Symbol"
                      required
                      helperText={
                        markets.isLoading ? 'Loading markets…' : 'The market to train on.'
                      }
                      slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Symbol' } }}
                    />
                  )}
                />
                <InfoTooltip label="Symbol" sections={SYMBOL_FIELD_HELP} />
              </Stack>

              <Stack direction="row" spacing={0.5} alignItems="flex-start">
                <Autocomplete
                  fullWidth
                  disabled={!symbol}
                  options={timeframes.data?.timeframes ?? []}
                  loading={timeframes.isLoading}
                  value={timeframe || null}
                  onChange={(_, next) => setTimeframe(next ?? '')}
                  noOptionsText={
                    symbol ? 'No timeframes match your search' : 'Select a symbol first'
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Timeframe"
                      required
                      helperText={
                        timeframes.isLoading
                          ? 'Loading timeframes…'
                          : 'The candle timeframe to load, e.g. 1h.'
                      }
                      slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Timeframe' } }}
                    />
                  )}
                />
                <InfoTooltip label="Timeframe" sections={TIMEFRAME_FIELD_HELP} />
              </Stack>

              <Stack direction="row" spacing={0.5} alignItems="flex-start">
                <TextField
                  fullWidth
                  label="Target column"
                  value={targetColumn}
                  onChange={(event) => setTargetColumn(event.target.value)}
                  helperText="Optional — defaults to the first built target column."
                  slotProps={{ htmlInput: { 'aria-label': 'Target column' } }}
                />
                <InfoTooltip label="Target column" sections={TARGET_COLUMN_FIELD_HELP} />
              </Stack>
            </Stack>
          ) : null}

          <TrainingSummaryPanel
            experiment={experimentDetail.data ?? null}
            datasetVersion={datasetVersion}
            modelLabel={selectedAdapter?.label ?? null}
            symbol={requiresRealData ? symbol : undefined}
            timeframe={requiresRealData ? timeframe : undefined}
          />

          <HyperparameterEditor
            knownValues={knownValues}
            onKnownChange={(key, value) => setKnownValues((prev) => ({ ...prev, [key]: value }))}
            customEntries={customEntries}
            onCustomChange={setCustomEntries}
          />

          {validationReasons.length > 0 ? (
            <Alert severity="warning" role="status">
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                Before you can create this job:
              </Typography>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {validationReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </Alert>
          ) : null}

          {create.isError ? (
            <Alert severity="error" role="alert">
              {create.error instanceof Error
                ? create.error.message
                : 'Could not create the training job.'}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!canSubmit}>
          {create.isPending ? 'Creating…' : 'Create Training Job'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
