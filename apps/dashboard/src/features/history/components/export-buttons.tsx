'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { fetchCandlePage } from '@/lib/api/market';
import type { Candle, CandlePage } from '@/types/api/market';
import type { HistoryQuery } from '../hooks/use-history-data';
import { buildEnvelope, envelopeToCsv, exportFileName } from '../lib/export';
import { formatNumber } from '../lib/format';

const MAX_EXPORT_PAGES = 250;

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function fetchAllCandles(
  query: HistoryQuery,
  onProgress: (fetched: number, total: number) => void,
): Promise<{ candles: Candle[]; page: CandlePage }> {
  const candles: Candle[] = [];
  let firstPage: CandlePage | null = null;
  let offset = 0;
  let total = Infinity;
  while (offset < total && candles.length < MAX_EXPORT_PAGES * query.limit) {
    const page = await fetchCandlePage(query.symbol, query.timeframe, {
      limit: query.limit,
      offset,
      start: query.start ?? undefined,
      end: query.end ?? undefined,
      sort: query.sort,
      dir: query.dir,
    });
    firstPage ??= page;
    candles.push(...page.items);
    total = page.pagination.total;
    offset += page.items.length;
    onProgress(candles.length, total);
    if (page.items.length === 0) {
      break;
    }
  }
  return { candles, page: firstPage as CandlePage };
}

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
      const { candles, page } = await fetchAllCandles(query, (fetched, total) =>
        setProgress({ fetched, total }),
      );
      const envelope = buildEnvelope(query, candles, page);
      const blob =
        kind === 'csv'
          ? new Blob([envelopeToCsv(envelope)], { type: 'text/csv;charset=utf-8' })
          : new Blob([JSON.stringify(envelope, null, 2)], {
              type: 'application/json;charset=utf-8',
            });
      download(blob, exportFileName(query, kind));
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
