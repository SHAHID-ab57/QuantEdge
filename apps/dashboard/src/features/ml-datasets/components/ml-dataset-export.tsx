'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { BuildMLDatasetParams } from '@/lib/api/ml-datasets';
import type { MLDatasetResponse } from '@/types/api/ml-datasets';
import { ExportSummaryDialog } from './export-summary-dialog';
import { EXPORT_FORMAT_OPTIONS, type ExportFormatOption } from '../lib/export-format';
import { useExportMLDataset } from '../hooks/use-ml-dataset-data';

export interface MLDatasetExportProps {
  symbol: string;
  timeframe: string;
  params: BuildMLDatasetParams;
  dataset: MLDatasetResponse;
  disabled?: boolean;
}

function exportFileName(symbol: string, timeframe: string, extension: string): string {
  const safe = (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, '-');
  return `${safe(symbol)}-${safe(timeframe)}-ml-dataset.${extension}`;
}

/**
 * CSV and JSON export for the current ML dataset — the target-appended,
 * split counterpart to `feature-engineering/components/dataset-export.tsx`.
 *
 * The file is built by the **backend**, not from the preview on screen,
 * for the exact same reason the plain feature export is: the preview is
 * capped for rendering, and only the backend can attach the full
 * versioning chain (pipeline, target pipeline, and builder versions, plus
 * the embedded validation verdict) the file needs to be reproducible. Both
 * formats include a `split` column, so the one downloaded file is the
 * complete train/validation/test artifact, not three separate ones.
 *
 * Clicking a format opens an `ExportSummaryDialog` first — rows, columns,
 * target, split, and an approximate size — rather than downloading
 * immediately, so a researcher sees what they're about to get before
 * committing to it. Format buttons are rendered from
 * `EXPORT_FORMAT_OPTIONS` rather than hardcoded, so a future format needs
 * no change here.
 */
export function MLDatasetExport({
  symbol,
  timeframe,
  params,
  dataset,
  disabled = false,
}: MLDatasetExportProps) {
  const exporter = useExportMLDataset();
  const [pendingFormat, setPendingFormat] = useState<ExportFormatOption['format'] | null>(null);
  const [confirming, setConfirming] = useState<ExportFormatOption['format'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runExport = async (format: ExportFormatOption['format']) => {
    setPendingFormat(format);
    setError(null);
    try {
      const blob = await exporter.mutateAsync({ symbol, params, format });
      downloadBlob(blob, exportFileName(symbol, timeframe, format));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The export failed.');
    } finally {
      setPendingFormat(null);
    }
  };

  const busy = pendingFormat !== null;

  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" color="text.secondary">
        Downloads the complete dataset — every row, not just the preview — with a per-row split
        label and the full version/validation provenance attached.
      </Typography>
      <Stack direction="row" spacing={1}>
        {EXPORT_FORMAT_OPTIONS.map((option) => (
          <Button
            key={option.format}
            variant="outlined"
            startIcon={<FileDownloadIcon />}
            disabled={disabled || busy}
            onClick={() => setConfirming(option.format)}
            aria-label={`Export ML dataset as ${option.format.toUpperCase()}`}
          >
            {pendingFormat === option.format ? 'Exporting…' : option.label}
          </Button>
        ))}
      </Stack>
      {error ? (
        <Alert severity="error" role="alert" sx={{ py: 0.5 }}>
          {error}
        </Alert>
      ) : null}

      <ExportSummaryDialog
        open={confirming !== null}
        format={confirming}
        rows={dataset.meta.total_rows}
        columns={dataset.columns.length}
        targetColumns={dataset.target_columns}
        splitRatios={dataset.split_ratios}
        busy={busy}
        onCancel={() => setConfirming(null)}
        onConfirm={() => {
          const format = confirming;
          setConfirming(null);
          if (format) {
            void runExport(format);
          }
        }}
      />
    </Stack>
  );
}
