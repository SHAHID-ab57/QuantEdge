'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import LinkIcon from '@mui/icons-material/Link';
import Button from '@mui/material/Button';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Snackbar from '@mui/material/Snackbar';
import { useState, type MouseEvent } from 'react';
import { env } from '@/config/env';
import { downloadBlob } from '@/lib/download-file';
import type { IndicatorCalculation } from '@/types/api/indicators';
import {
  buildApiRequestUrl,
  buildCsv,
  buildJson,
  buildValuesText,
  exportFileName,
} from '../lib/export';

export interface ExportMenuProps {
  result: IndicatorCalculation;
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
 * Researcher utilities for one calculation: download it as CSV or JSON,
 * copy the values table for pasting into a spreadsheet, or copy the exact
 * REST request that produced it. Every builder lives in `lib/export.ts` as
 * a pure function — this component only wires them to a download/clipboard
 * side effect and reports success or failure.
 */
export function ExportMenu({ result }: ExportMenuProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const close = () => setAnchor(null);

  const handleExportCsv = () => {
    downloadBlob(
      new Blob([buildCsv(result)], { type: 'text/csv;charset=utf-8' }),
      exportFileName(result, 'csv'),
    );
    close();
  };

  const handleExportJson = () => {
    downloadBlob(
      new Blob([buildJson(result)], { type: 'application/json;charset=utf-8' }),
      exportFileName(result, 'json'),
    );
    close();
  };

  const handleCopyValues = async () => {
    const ok = await copyText(buildValuesText(result));
    setFeedback(ok ? 'Values copied to clipboard' : 'Could not access the clipboard');
    close();
  };

  const handleCopyRequest = async () => {
    const url = buildApiRequestUrl(
      env.NEXT_PUBLIC_API_URL,
      result.symbol,
      result.indicator.name,
      result.timeframe,
      Object.fromEntries(
        Object.entries(result.parameters).map(([key, value]) => [key, String(value)]),
      ),
    );
    const ok = await copyText(url);
    setFeedback(ok ? 'API request copied to clipboard' : 'Could not access the clipboard');
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
        Export
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
        <MenuItem onClick={handleCopyRequest}>
          <ListItemIcon>
            <LinkIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Copy API Request</ListItemText>
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
