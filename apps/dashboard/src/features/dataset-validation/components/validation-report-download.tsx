'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import Button from '@mui/material/Button';
import { downloadBlob } from '@/lib/download-file';
import type { ValidationReport } from '@/types/api/dataset-validation';
import { reportFilename } from '../lib/report-filename';

export interface ValidationReportDownloadProps {
  report: ValidationReport;
}

/**
 * Downloads the full validation report as a JSON file.
 *
 * The report is already in hand from the validation call — there is no
 * second backend request here, unlike the Feature Engineering page's
 * dataset export (which must re-fetch the *complete*, untruncated dataset
 * from the server). A validation report is never truncated in the first
 * place, so serializing the object already on screen is the complete
 * report, not a partial one.
 */
export function ValidationReportDownload({ report }: ValidationReportDownloadProps) {
  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: 'application/json',
    });
    downloadBlob(blob, reportFilename(report));
  };

  return (
    <Button
      variant="outlined"
      size="small"
      startIcon={<FileDownloadIcon />}
      onClick={download}
      aria-label="Download validation report as JSON"
    >
      Download Report
    </Button>
  );
}
