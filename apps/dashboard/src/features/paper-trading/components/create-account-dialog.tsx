'use client';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState } from 'react';

export interface CreateAccountDialogProps {
  open: boolean;
  submitting: boolean;
  onCancel: () => void;
  onCreate: (values: { name: string | null; startingBalance: string }) => void;
}

const DEFAULT_STARTING_BALANCE = '100000';

/** Open a new virtual trading account: an optional label, and a starting
 * cash balance. */
export function CreateAccountDialog({
  open,
  submitting,
  onCancel,
  onCreate,
}: CreateAccountDialogProps) {
  const [name, setName] = useState('');
  const [startingBalance, setStartingBalance] = useState(DEFAULT_STARTING_BALANCE);

  const parsed = Number(startingBalance);
  const canSubmit = startingBalance.trim() !== '' && Number.isFinite(parsed) && parsed > 0;

  const handleCreate = () => {
    if (!canSubmit) return;
    onCreate({ name: name.trim() || null, startingBalance });
  };

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>Open a Paper Trading Account</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Account name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            helperText="Optional — a label for your own reference."
            slotProps={{ htmlInput: { 'aria-label': 'Account name' } }}
          />
          <TextField
            label="Starting balance"
            value={startingBalance}
            onChange={(event) => setStartingBalance(event.target.value)}
            helperText="Virtual cash — no real money is ever involved."
            slotProps={{ htmlInput: { 'aria-label': 'Starting balance', inputMode: 'decimal' } }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleCreate} disabled={!canSubmit || submitting}>
          {submitting ? 'Creating…' : 'Create Account'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
