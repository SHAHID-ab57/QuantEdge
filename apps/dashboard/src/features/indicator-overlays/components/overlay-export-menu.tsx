'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Button from '@mui/material/Button';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Snackbar from '@mui/material/Snackbar';
import { useState, type MouseEvent } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { OverlayChartSeries } from '../lib/overlay-series';
import {
  buildOverlayCsv,
  buildOverlayJson,
  buildOverlayValuesText,
  overlayExportFileName,
  type OverlayExportContext,
} from '../lib/overlay-export';

export interface OverlayExportMenuProps {
  symbol: string;
  timeframe: string;
  overlays: OverlayChartSeries[];
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * CSV / JSON / copy-to-clipboard for the *current overlay set* on a
 * chart — the Overlay System's counterpart to the standalone `/indicators`
 * page's per-calculation `ExportMenu`, reusing the same
 * Button+Menu+Snackbar pattern and `downloadBlob` helper so the two
 * surfaces feel identical even though they export different shapes of data.
 */
export function OverlayExportMenu({ symbol, timeframe, overlays }: OverlayExportMenuProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const close = () => setAnchor(null);
  const ctx: OverlayExportContext = { symbol, timeframe, overlays };

  const handleExportCsv = () => {
    downloadBlob(
      new Blob([buildOverlayCsv(ctx)], { type: 'text/csv;charset=utf-8' }),
      overlayExportFileName(symbol, 'csv'),
    );
    close();
  };

  const handleExportJson = () => {
    downloadBlob(
      new Blob([buildOverlayJson(ctx)], { type: 'application/json;charset=utf-8' }),
      overlayExportFileName(symbol, 'json'),
    );
    close();
  };

  const handleCopyValues = async () => {
    const ok = await copyText(buildOverlayValuesText(ctx));
    setFeedback(ok ? 'Overlay values copied to clipboard' : 'Could not access the clipboard');
    close();
  };

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={<FileDownloadIcon />}
        onClick={(event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget)}
        aria-haspopup="menu"
      >
        Export overlays
      </Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={close}>
        <MenuItem onClick={handleExportCsv}>
          <ListItemIcon>
            <FileDownloadIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Export CSV</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleExportJson}>
          <ListItemIcon>
            <FileDownloadIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Export JSON</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleCopyValues}>
          <ListItemIcon>
            <ContentCopyIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Copy Values</ListItemText>
        </MenuItem>
      </Menu>
      <Snackbar
        open={feedback !== null}
        autoHideDuration={4000}
        onClose={() => setFeedback(null)}
        message={feedback}
      />
    </>
  );
}
