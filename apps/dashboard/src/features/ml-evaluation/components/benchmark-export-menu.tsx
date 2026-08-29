'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Button from '@mui/material/Button';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import { useState, type MouseEvent } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { BenchmarkResponse } from '@/types/api/evaluation';
import {
  BENCHMARK_EXPORTERS,
  benchmarkExportFileName,
  type BenchmarkExportFormat,
} from '../lib/benchmark-export';

export interface BenchmarkExportMenuProps {
  response: BenchmarkResponse;
  datasetVersion: string | null;
}

/**
 * Export the current comparison as CSV or JSON — every format this menu
 * offers comes straight from `BENCHMARK_EXPORTERS`
 * (`lib/benchmark-export.ts`), so a future PDF entry appears here with no
 * change to this component, the same extension guarantee this platform's
 * other Strategy + Registry contexts already give. Mirrors
 * `features/indicators/components/export-menu.tsx`'s own Button+Menu shape.
 */
export function BenchmarkExportMenu({ response, datasetVersion }: BenchmarkExportMenuProps) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const close = () => setAnchor(null);

  const handleExport = (format: BenchmarkExportFormat) => {
    const exporter = BENCHMARK_EXPORTERS[format];
    const result = exporter.build(response);
    downloadBlob(
      new Blob([result.content], { type: result.mimeType }),
      benchmarkExportFileName(format, datasetVersion),
    );
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
        {(Object.keys(BENCHMARK_EXPORTERS) as BenchmarkExportFormat[]).map((format) => (
          <MenuItem key={format} onClick={() => handleExport(format)}>
            <ListItemIcon>
              <FileDownloadIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Export {BENCHMARK_EXPORTERS[format].label}</ListItemText>
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}
