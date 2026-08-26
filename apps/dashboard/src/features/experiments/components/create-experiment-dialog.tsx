'use client';

import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState } from 'react';
import { EXPERIMENT_STATUSES, type ExperimentStatus } from '@/types/api/experiments';
import { useCreateExperiment } from '../hooks/use-experiments-data';
import { statusLabel } from '../lib/experiment-status';

export interface CreateExperimentDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}

/**
 * Registers a new experiment: name, dataset version, model type (a
 * placeholder label only — no training engine exists yet), status, notes,
 * and tags. Feature set / target config / split config are not editable
 * here — a researcher typically copies those verbatim from the ML Dataset
 * Builder's own dataset config (see `/ml-datasets`'s "Copy Configuration")
 * rather than retyping them, so this form focuses on the fields an
 * experiment record adds on top of a dataset build: identity, outcome
 * tracking, and commentary.
 */
export function CreateExperimentDialog({ open, onClose, onCreated }: CreateExperimentDialogProps) {
  const create = useCreateExperiment();
  const [name, setName] = useState('');
  const [datasetVersion, setDatasetVersion] = useState('');
  const [modelType, setModelType] = useState('');
  const [status, setStatus] = useState<ExperimentStatus>('draft');
  const [notes, setNotes] = useState('');
  const [tags, setTags] = useState<string[]>([]);

  const reset = () => {
    setName('');
    setDatasetVersion('');
    setModelType('');
    setStatus('draft');
    setNotes('');
    setTags([]);
    create.reset();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    const created = await create.mutateAsync({
      name: name.trim(),
      dataset_version: datasetVersion.trim() || null,
      model_type: modelType.trim() || null,
      status,
      notes: notes.trim() || null,
      tags,
    });
    reset();
    onCreated(created.id);
  };

  const canSubmit = name.trim().length > 0 && !create.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Register a New Experiment</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Name"
            required
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            slotProps={{ htmlInput: { 'aria-label': 'Experiment name' } }}
          />
          <TextField
            label="Dataset version"
            placeholder="ml_dataset_id, e.g. 9c1e4a2c-..."
            value={datasetVersion}
            onChange={(event) => setDatasetVersion(event.target.value)}
            helperText="The ML Dataset Builder's ml_dataset_id this experiment was built over."
          />
          <TextField
            label="Model type"
            placeholder="e.g. xgboost_baseline (placeholder only)"
            value={modelType}
            onChange={(event) => setModelType(event.target.value)}
            helperText="A label only — no training engine exists on this platform yet."
          />
          <TextField
            select
            label="Status"
            value={status}
            onChange={(event) => setStatus(event.target.value as ExperimentStatus)}
          >
            {EXPERIMENT_STATUSES.map((option) => (
              <MenuItem key={option} value={option}>
                {statusLabel(option)}
              </MenuItem>
            ))}
          </TextField>
          <Autocomplete
            multiple
            freeSolo
            options={[]}
            value={tags}
            onChange={(_, next) => setTags(next as string[])}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Tags"
                placeholder="Type a tag and press Enter"
                slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Tags' } }}
              />
            )}
          />
          <TextField
            label="Notes"
            multiline
            minRows={3}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
          {create.isError ? (
            <Alert severity="error" role="alert">
              {create.error instanceof Error
                ? create.error.message
                : 'Could not create the experiment.'}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!canSubmit}>
          {create.isPending ? 'Creating…' : 'Create Experiment'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
