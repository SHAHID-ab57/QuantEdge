'use client';

import EditIcon from '@mui/icons-material/Edit';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

export interface ExperimentNotesCardProps {
  notes: string | null;
  onSave: (notes: string) => void;
  saving?: boolean;
}

/** Free-form researcher commentary — view by default, edit on demand. */
export function ExperimentNotesCard({ notes, onSave, saving = false }: ExperimentNotesCardProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(notes ?? '');

  const startEditing = () => {
    setDraft(notes ?? '');
    setEditing(true);
  };

  const handleSave = () => {
    onSave(draft);
    setEditing(false);
  };

  if (!editing) {
    return (
      <Stack spacing={1} aria-label="Experiment notes">
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Notes
          </Typography>
          <IconButton size="small" aria-label="Edit notes" onClick={startEditing}>
            <EditIcon fontSize="small" />
          </IconButton>
        </Stack>
        <Typography variant="body2" color={notes ? 'text.primary' : 'text.secondary'}>
          {notes || 'No notes yet.'}
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={1} aria-label="Edit experiment notes">
      <TextField
        multiline
        minRows={4}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        slotProps={{ htmlInput: { 'aria-label': 'Notes' } }}
        autoFocus
      />
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
        <Button size="small" onClick={() => setEditing(false)} disabled={saving}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}
