'use client';

import DownloadIcon from '@mui/icons-material/Download';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Typography from '@mui/material/Typography';
import { useMemo, useState } from 'react';
import { downloadBlob } from '@/lib/download-file';

export interface FeatureImportanceRow {
  feature: string;
  coefficient: number;
  abs_importance: number;
  sign: 'positive' | 'negative' | 'neutral';
}

export interface FeatureImportancePanelProps {
  rows: unknown;
  onDownloadCsv?: () => Promise<Blob>;
}

type SortKey = 'feature' | 'coefficient' | 'abs_importance';

function isFeatureImportanceRows(value: unknown): value is FeatureImportanceRow[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        typeof row === 'object' &&
        row !== null &&
        typeof (row as Record<string, unknown>).feature === 'string' &&
        typeof (row as Record<string, unknown>).coefficient === 'number' &&
        typeof (row as Record<string, unknown>).abs_importance === 'number',
    )
  );
}

function signColor(sign: string): 'success.main' | 'error.main' | 'text.disabled' {
  if (sign === 'positive') return 'success.main';
  if (sign === 'negative') return 'error.main';
  return 'text.disabled';
}

/**
 * A sortable feature-coefficient table plus a horizontal bar visualization —
 * the Model Interpretability view for `logistic_regression`/`linear_regression`
 * jobs. Renders nothing when `rows` isn't the shape the backend's
 * `compute_feature_importance` produces, rather than guessing a fallback.
 */
export function FeatureImportancePanel({ rows, onDownloadCsv }: FeatureImportancePanelProps) {
  const [sortKey, setSortKey] = useState<SortKey>('abs_importance');
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc');

  const parsed = isFeatureImportanceRows(rows) ? rows : null;

  const sorted = useMemo(() => {
    if (!parsed) return [];
    const copy = [...parsed];
    copy.sort((a, b) => {
      const left = a[sortKey];
      const right = b[sortKey];
      const cmp =
        typeof left === 'string' ? left.localeCompare(right as string) : left - (right as number);
      return direction === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [parsed, sortKey, direction]);

  if (!parsed || parsed.length === 0) {
    return null;
  }

  const maxAbsImportance = Math.max(...parsed.map((row) => row.abs_importance), 1e-9);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setDirection(direction === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setDirection('desc');
    }
  };

  const handleDownload = async () => {
    if (!onDownloadCsv) return;
    const blob = await onDownloadCsv();
    downloadBlob(blob, 'feature_importance.csv');
  };

  return (
    <Stack spacing={1}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          Feature Importance
        </Typography>
        {onDownloadCsv ? (
          <Button size="small" startIcon={<DownloadIcon />} onClick={handleDownload}>
            Download CSV
          </Button>
        ) : null}
      </Stack>
      <TableContainer>
        <Table size="small" aria-label="Feature importance">
          <TableHead>
            <TableRow>
              <TableCell sortDirection={sortKey === 'feature' ? direction : false}>
                <TableSortLabel
                  active={sortKey === 'feature'}
                  direction={sortKey === 'feature' ? direction : 'asc'}
                  onClick={() => handleSort('feature')}
                >
                  Feature
                </TableSortLabel>
              </TableCell>
              <TableCell
                align="right"
                sortDirection={sortKey === 'coefficient' ? direction : false}
              >
                <TableSortLabel
                  active={sortKey === 'coefficient'}
                  direction={sortKey === 'coefficient' ? direction : 'asc'}
                  onClick={() => handleSort('coefficient')}
                >
                  Coefficient
                </TableSortLabel>
              </TableCell>
              <TableCell
                align="right"
                sortDirection={sortKey === 'abs_importance' ? direction : false}
              >
                <TableSortLabel
                  active={sortKey === 'abs_importance'}
                  direction={sortKey === 'abs_importance' ? direction : 'asc'}
                  onClick={() => handleSort('abs_importance')}
                >
                  Importance
                </TableSortLabel>
              </TableCell>
              <TableCell>Sign</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sorted.map((row) => (
              <TableRow key={row.feature}>
                <TableCell>{row.feature}</TableCell>
                <TableCell align="right">{row.coefficient.toFixed(4)}</TableCell>
                <TableCell align="right">
                  <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
                    <Box
                      sx={{
                        height: 8,
                        width: `${Math.max((row.abs_importance / maxAbsImportance) * 60, 2)}px`,
                        bgcolor: signColor(row.sign),
                        borderRadius: 0.5,
                      }}
                      aria-hidden
                    />
                    <span>{row.abs_importance.toFixed(4)}</span>
                  </Stack>
                </TableCell>
                <TableCell sx={{ color: signColor(row.sign), textTransform: 'capitalize' }}>
                  {row.sign}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}
