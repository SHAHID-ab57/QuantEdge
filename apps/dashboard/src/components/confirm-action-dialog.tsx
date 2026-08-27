'use client';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';

export interface ConfirmActionDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busyLabel: string;
  color?: 'error' | 'warning' | 'primary';
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * A generic "are you sure" dialog, mirroring
 * `experiments/components/delete-experiment-dialog.tsx`'s exact shape but
 * parameterized so unrelated destructive-ish actions across features share
 * one implementation rather than each declaring its own near-identical
 * dialog — originally built for the ML Training page's Delete/Cancel Job
 * actions, promoted here once Dataset History's delete-a-build action
 * needed the identical behavior.
 */
export function ConfirmActionDialog({
  open,
  title,
  description,
  confirmLabel,
  busyLabel,
  color = 'error',
  busy = false,
  onCancel,
  onConfirm,
}: ConfirmActionDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{description}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={busy}>
          Back
        </Button>
        <Button color={color} variant="contained" onClick={onConfirm} disabled={busy}>
          {busy ? busyLabel : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
