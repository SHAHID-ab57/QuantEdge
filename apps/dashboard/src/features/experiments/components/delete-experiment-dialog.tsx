'use client';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

export interface DeleteExperimentDialogProps {
  open: boolean;
  experimentName: string;
  onCancel: () => void;
  onConfirm: () => void;
  busy?: boolean;
}

export function DeleteExperimentDialog({
  open,
  experimentName,
  onCancel,
  onConfirm,
  busy = false,
}: DeleteExperimentDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>Delete Experiment</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Permanently delete <strong>{experimentName}</strong>, along with all of its recorded
          metrics and artifact references? This cannot be undone.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button color="error" variant="contained" onClick={onConfirm} disabled={busy}>
          {busy ? 'Deleting…' : 'Delete'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
