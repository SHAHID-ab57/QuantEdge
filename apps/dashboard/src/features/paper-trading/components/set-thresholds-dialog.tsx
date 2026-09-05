'use client';

import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';

export interface SetThresholdsDialogProps {
  open: boolean;
  symbol: string | null;
  currentStopLossPrice: string | null;
  currentTakeProfitPrice: string | null;
  submitting: boolean;
  onCancel: () => void;
  onSave: (values: { stopLossPrice: string | null; takeProfitPrice: string | null }) => void;
}

function isValidOptionalPrice(value: string): boolean {
  if (value.trim() === '') return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

/**
 * Set, update, or clear one position's stop-loss/take-profit —
 * `PATCH .../positions/{symbol}`, independent of placing any order.
 * Seeded from the position's own current values whenever it opens, so
 * editing shows what's already set rather than a blank form. A field
 * left blank is saved as an explicit clear (sent as `null`), never
 * "leave unchanged" — this dialog always edits the position's *whole*
 * current state, not a partial patch typed from nothing.
 */
export function SetThresholdsDialog({
  open,
  symbol,
  currentStopLossPrice,
  currentTakeProfitPrice,
  submitting,
  onCancel,
  onSave,
}: SetThresholdsDialogProps) {
  const [stopLossPrice, setStopLossPrice] = useState('');
  const [takeProfitPrice, setTakeProfitPrice] = useState('');

  useEffect(() => {
    if (open) {
      setStopLossPrice(currentStopLossPrice ?? '');
      setTakeProfitPrice(currentTakeProfitPrice ?? '');
    }
  }, [open, currentStopLossPrice, currentTakeProfitPrice]);

  const validStopLoss = isValidOptionalPrice(stopLossPrice);
  const validTakeProfit = isValidOptionalPrice(takeProfitPrice);
  const canSave = validStopLoss && validTakeProfit;

  const handleSave = () => {
    if (!canSave) return;
    onSave({
      stopLossPrice: stopLossPrice.trim() === '' ? null : stopLossPrice,
      takeProfitPrice: takeProfitPrice.trim() === '' ? null : takeProfitPrice,
    });
  };

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
      <DialogTitle>Stop-Loss / Take-Profit{symbol ? ` — ${symbol}` : ''}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Closes this position automatically the instant the live price crosses either level.
            Leave a field blank to clear it.
          </Typography>
          <TextField
            label="Stop-loss price"
            value={stopLossPrice}
            onChange={(event) => setStopLossPrice(event.target.value)}
            error={!validStopLoss}
            helperText={
              validStopLoss ? 'Must be below the current price.' : 'Must be a positive number.'
            }
            slotProps={{
              htmlInput: { 'aria-label': 'Edit stop-loss price', inputMode: 'decimal' },
            }}
          />
          <TextField
            label="Take-profit price"
            value={takeProfitPrice}
            onChange={(event) => setTakeProfitPrice(event.target.value)}
            error={!validTakeProfit}
            helperText={
              validTakeProfit ? 'Must be above the current price.' : 'Must be a positive number.'
            }
            slotProps={{
              htmlInput: { 'aria-label': 'Edit take-profit price', inputMode: 'decimal' },
            }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSave} disabled={!canSave || submitting}>
          {submitting ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
