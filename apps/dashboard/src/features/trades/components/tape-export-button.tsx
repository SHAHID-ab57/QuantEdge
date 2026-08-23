'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Button from '@mui/material/Button';
import Tooltip from '@mui/material/Tooltip';
import { useCallback } from 'react';
import type { LiveTradeData } from '@/types/api/market-stream';
import { tapeExportFileName, tradesToCsv } from '../lib/tape-export';

export interface TapeExportButtonProps {
  trades: LiveTradeData[];
  symbol: string;
  sideFilter: string;
  minSize: number;
}

/**
 * Same anchor-click download mechanism the History page's exports use — not
 * extracted into a shared helper, since it is six lines and the two call
 * sites share no other logic (History fetches and paginates a whole query
 * first; this one exports what is already on screen).
 */
function download(contents: string, filename: string) {
  const blob = new Blob([contents], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Exports exactly the rows currently visible in the tape — the active
 * side/minimum-size filters and row cap included — with a metadata block
 * recording those filters, so the file is self-describing. See
 * `lib/tape-export.ts` for why "visible rows" is the right scope rather
 * than the whole session.
 */
export function TapeExportButton({ trades, symbol, sideFilter, minSize }: TapeExportButtonProps) {
  const handleExport = useCallback(() => {
    download(tradesToCsv(trades, { symbol, sideFilter, minSize }), tapeExportFileName(symbol));
  }, [trades, symbol, sideFilter, minSize]);

  return (
    <Tooltip title="Downloads the rows currently visible in the tape, with the active filters recorded in the file.">
      <span>
        <Button
          size="small"
          variant="outlined"
          startIcon={<FileDownloadIcon />}
          onClick={handleExport}
          disabled={trades.length === 0}
          aria-label="Export visible trade tape rows as CSV"
        >
          Export CSV
        </Button>
      </span>
    </Tooltip>
  );
}
