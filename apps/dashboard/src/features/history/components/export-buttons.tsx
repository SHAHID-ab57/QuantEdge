'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { fetchAllCandles } from '@/lib/api/paginate-candles';
import { downloadBlob } from '@/lib/download-file';
import type { HistoryQuery } from '../hooks/use-history-data';
import { buildEnvelope, envelopeToCsv, exportFileName } from '../lib/export';
import { formatNumber } from '../lib/format';

interface ExportButtonsProps {
  query: HistoryQuery;
  disabled: boolean;
}

export function ExportButtons({ query, disabled }: ExportButtonsProps) {
  const [exporting, setExporting] = useState<'csv' | 'json' | null>(null);
  const [progress, setProgress] = useState<{ fetched: number; total: number } | null>(null);

  const runExport = async (kind: 'csv' | 'json') => {
    setExporting(kind);
    setProgress(null);
    try {
      const { candles, firstPage } = await fetchAllCandles(query, (fetched, total) =>
        setProgress({ fetched, total }),
      );
      const envelope = buildEnvelope(query, candles, firstPage);
      const blob =
        kind === 'csv'
          ? new Blob([envelopeToCsv(envelope)], { type: 'text/csv;charset=utf-8' })
          : new Blob([JSON.stringify(envelope, null, 2)], {
              type: 'application/json;charset=utf-8',
            });
      downloadBlob(blob, exportFileName(query, kind));
    } finally {
      setExporting(null);
      setProgress(null);
    }
  };

  const busy = exporting !== null || disabled;

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }} aria-label="Export candles">
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="h6" component="h2" gutterBottom>
            Export
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Downloads every candle matching the current filters, with the backend-computed
            statistics and quality metrics attached
            {progress
              ? ` (${formatNumber(progress.fetched)} of ${formatNumber(progress.total)} fetched)`
              : ''}
            .
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<FileDownloadIcon />}
            disabled={busy}
            onClick={() => runExport('csv')}
            aria-label="Export candles as CSV"
          >
            {exporting === 'csv' ? 'Exporting…' : 'CSV'}
          </Button>
          <Button
            variant="outlined"
            startIcon={<FileDownloadIcon />}
            disabled={busy}
            onClick={() => runExport('json')}
            aria-label="Export candles as JSON"
          >
            {exporting === 'json' ? 'Exporting…' : 'JSON'}
          </Button>
        </Stack>
      </Stack>
    </Paper>
  );
}
