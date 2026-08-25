'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { BuildDatasetParams } from '@/lib/api/features';
import { useExportDataset } from '../hooks/use-feature-data';

export interface DatasetExportProps {
  symbol: string;
  timeframe: string;
  params: BuildDatasetParams;
  disabled?: boolean;
}

function exportFileName(symbol: string, timeframe: string, extension: string): string {
  const safe = (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, '-');
  return `${safe(symbol)}-${safe(timeframe)}-features.${extension}`;
}

/**
 * CSV and JSON export for the current dataset.
 *
 * The file is built by the **backend**, not from the preview on screen —
 * see `exportFeatureDataset`. The preview is capped for rendering, so
 * serializing it here would silently ship a partial training set, and the
 * backend is also the only place that can attach the pipeline and feature
 * versions the file needs to be reproducible.
 *
 * A failed export is surfaced inline rather than swallowed: an export
 * button that appears to do nothing is indistinguishable from a browser
 * blocking the download, and a researcher has no way to tell which
 * happened.
 */
export function DatasetExport({ symbol, timeframe, params, disabled = false }: DatasetExportProps) {
  const exporter = useExportDataset();
  const [pending, setPending] = useState<'csv' | 'json' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runExport = async (format: 'csv' | 'json') => {
    setPending(format);
    setError(null);
    try {
      const blob = await exporter.mutateAsync({ symbol, params, format });
      downloadBlob(blob, exportFileName(symbol, timeframe, format));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The export failed.');
    } finally {
      setPending(null);
    }
  };

  const busy = pending !== null;

  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" color="text.secondary">
        Downloads the complete dataset — not just the preview — with the pipeline version and every
        feature&apos;s resolved parameters attached.
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button
          variant="outlined"
          startIcon={<FileDownloadIcon />}
          disabled={disabled || busy}
          onClick={() => runExport('csv')}
          aria-label="Export dataset as CSV"
        >
          {pending === 'csv' ? 'Exporting…' : 'CSV'}
        </Button>
        <Button
          variant="outlined"
          startIcon={<FileDownloadIcon />}
          disabled={disabled || busy}
          onClick={() => runExport('json')}
          aria-label="Export dataset as JSON"
        >
          {pending === 'json' ? 'Exporting…' : 'JSON'}
        </Button>
      </Stack>
      {error ? (
        <Alert severity="error" role="alert" sx={{ py: 0.5 }}>
          {error}
        </Alert>
      ) : null}
    </Stack>
  );
}
