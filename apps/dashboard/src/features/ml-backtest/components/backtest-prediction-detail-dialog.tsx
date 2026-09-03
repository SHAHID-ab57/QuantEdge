'use client';

import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { PredictionResultPanel } from '@/features/ml-predict/components/prediction-result-panel';
import { usePrediction } from '@/features/ml-predict/hooks/use-prediction-data';

export interface BacktestPredictionDetailDialogProps {
  predictionId: string | null;
  onClose: () => void;
}

/**
 * One backtest step's own prediction, reopened from the drill-down table —
 * reuses `usePrediction`/`PredictionResultPanel` verbatim (the exact hook
 * and component the Live Prediction page itself uses to reopen a row from
 * Prediction History), never a second "show one prediction" view built for
 * backtest rows specifically.
 */
export function BacktestPredictionDetailDialog({
  predictionId,
  onClose,
}: BacktestPredictionDetailDialogProps) {
  const prediction = usePrediction(predictionId);
  if (!predictionId) return null;

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Backtest Step Prediction</DialogTitle>
      <DialogContent>
        {prediction.data ? <PredictionResultPanel prediction={prediction.data} /> : null}
      </DialogContent>
    </Dialog>
  );
}
