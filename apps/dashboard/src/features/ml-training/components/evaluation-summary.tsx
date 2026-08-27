'use client';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import type { ModelKind } from '@/types/api/training';
import { ConfusionMatrixDetailsTable } from './confusion-matrix-details-table';
import { FeatureImportancePanel } from './feature-importance-panel';
import { ModelMetadataPanel } from './model-metadata-panel';
import { PredictionSamplesTable } from './prediction-samples-table';
import { RocPrCurveCharts } from './roc-pr-curve-charts';
import { TrainValTestMetricsTable } from './train-val-test-metrics-table';

export interface EvaluationSummaryProps {
  modelKind: ModelKind | undefined;
  metrics: Record<string, unknown>;
  summary: Record<string, unknown>;
  onDownloadFeatureImportanceCsv?: () => Promise<Blob>;
}

const CLASSIFICATION_METRIC_LABELS: Record<string, string> = {
  accuracy: 'Accuracy',
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1',
};

const REGRESSION_METRIC_LABELS: Record<string, string> = {
  mae: 'MAE',
  mse: 'MSE',
  rmse: 'RMSE',
  r2: 'R²',
};

function formatMetricValue(value: unknown): string {
  return typeof value === 'number' ? value.toFixed(4) : String(value);
}

function MetricsTable({
  labels,
  metrics,
}: {
  labels: Record<string, string>;
  metrics: Record<string, unknown>;
}) {
  const rows = Object.entries(labels).filter(([key]) => key in metrics);
  return (
    <TableContainer>
      <Table size="small" aria-label="Evaluation metrics">
        <TableHead>
          <TableRow>
            {rows.map(([key, label]) => (
              <TableCell key={key}>{label}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          <TableRow>
            {rows.map(([key]) => (
              <TableCell key={key}>{formatMetricValue(metrics[key])}</TableCell>
            ))}
          </TableRow>
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function ConfusionMatrix({ classes, matrix }: { classes: string[]; matrix: number[][] }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Confusion Matrix
      </Typography>
      <TableContainer>
        <Table size="small" aria-label="Confusion matrix">
          <TableHead>
            <TableRow>
              <TableCell />
              <TableCell colSpan={classes.length} align="center">
                Predicted
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Actual</TableCell>
              {classes.map((label) => (
                <TableCell key={label} align="right">
                  {label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {matrix.map((row, rowIndex) => (
              <TableRow key={rowIndex}>
                <TableCell sx={{ fontWeight: 600 }}>{classes[rowIndex]}</TableCell>
                {row.map((cell, cellIndex) => (
                  <TableCell key={cellIndex} align="right">
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

function isNumberMatrix(value: unknown): value is number[][] {
  return Array.isArray(value) && value.every((row) => Array.isArray(row));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

/**
 * Renders a completed job's evaluation results appropriately for its model
 * kind — a confusion matrix for a classifier, MAE/MSE/RMSE/R² for a
 * regressor, or a generic metrics list for the placeholder adapter (which
 * declares no `model_kind` beyond `"placeholder"`). `modelKind` comes from
 * the model adapter catalogue (`GET /training-jobs/models`), looked up by
 * the job's own `model_type` — never guessed from the shape of `summary`.
 */
export function EvaluationSummary({
  modelKind,
  metrics,
  summary,
  onDownloadFeatureImportanceCsv,
}: EvaluationSummaryProps) {
  if (modelKind === 'classification') {
    const classes = summary.classes;
    const matrix = summary.confusion_matrix;
    return (
      <Stack spacing={1.5}>
        <MetricsTable labels={CLASSIFICATION_METRIC_LABELS} metrics={metrics} />
        {isStringArray(classes) && isNumberMatrix(matrix) ? (
          <ConfusionMatrix classes={classes} matrix={matrix} />
        ) : null}
        <ConfusionMatrixDetailsTable details={summary.confusion_matrix_details} />
        <TrainValTestMetricsTable
          trainMetrics={summary.train_metrics}
          validationMetrics={metrics}
          testMetrics={summary.test_metrics}
          overfitting={summary.overfitting}
        />
        <RocPrCurveCharts rocPrCurves={summary.roc_pr_curves} />
        <FeatureImportancePanel
          rows={summary.feature_importance}
          onDownloadCsv={onDownloadFeatureImportanceCsv}
        />
        <PredictionSamplesTable samples={summary.prediction_samples} />
        <ModelMetadataPanel metadata={summary.model_metadata} />
      </Stack>
    );
  }

  if (modelKind === 'regression') {
    return (
      <Stack spacing={1.5}>
        <MetricsTable labels={REGRESSION_METRIC_LABELS} metrics={metrics} />
        <TrainValTestMetricsTable
          trainMetrics={summary.train_metrics}
          validationMetrics={metrics}
          testMetrics={summary.test_metrics}
          overfitting={summary.overfitting}
        />
        <FeatureImportancePanel
          rows={summary.feature_importance}
          onDownloadCsv={onDownloadFeatureImportanceCsv}
        />
        <PredictionSamplesTable samples={summary.prediction_samples} />
        <ModelMetadataPanel metadata={summary.model_metadata} />
      </Stack>
    );
  }

  return (
    <Stack spacing={0.25}>
      {Object.entries(metrics).map(([name, value]) => (
        <Typography key={name} variant="body2" color="text.secondary">
          {name}: {String(value)}
        </Typography>
      ))}
    </Stack>
  );
}
