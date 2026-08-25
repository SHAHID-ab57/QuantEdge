'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { memo, useMemo, useRef, useState, type UIEvent } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import type { FeatureDataset } from '@/types/api/features';
import { formatCell } from '../lib/feature-selection';

export interface DatasetPreviewTableProps {
  dataset: FeatureDataset;
  /** Rows to render; the response may already be truncated server-side. */
  maxRows?: number;
}

/** Fixed row height (px) the virtualization math is built on — every row renders identically. */
const ROW_HEIGHT = 33;
/** The scrollable area's height; also what bounds how many rows are ever mounted at once. */
const TABLE_HEIGHT = 460;
/** Extra rows rendered beyond the visible window on each side, so a fast scroll never flashes blank space. */
const OVERSCAN = 8;

/**
 * The dataset matrix as a scrollable, **virtualized** table: one row per
 * timestamp, one column per feature output.
 *
 * Only mounts the rows currently scrolled into view (plus a small overscan
 * margin) — never the whole dataset. Two blank spacer rows (`height:
 * remainingRows * ROW_HEIGHT`) stand in for everything above and below the
 * visible window, which is what keeps the scrollbar's size and position
 * correct without every row actually existing in the DOM. This is what
 * keeps a 100,000+ row dataset's preview exactly as responsive as a
 * 100-row one — without pulling in a virtualization library for a table
 * this codebase would otherwise have no other use for.
 *
 * Every column header carries its declared `dtype` and description, because
 * a researcher reading a feature matrix needs to know whether a column is a
 * continuous value or a categorical *before* deciding how to model it —
 * that is the difference between scaling a column and one-hot encoding it,
 * and the column name alone rarely says which.
 */
function DatasetPreviewTableInner({ dataset, maxRows }: DatasetPreviewTableProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const rows = useMemo(
    () => (maxRows === undefined ? dataset.rows : dataset.rows.slice(0, maxRows)),
    [dataset.rows, maxRows],
  );
  const timestamps = useMemo(
    () => (maxRows === undefined ? dataset.timestamps : dataset.timestamps.slice(0, maxRows)),
    [dataset.timestamps, maxRows],
  );

  const { startIndex, endIndex, topSpacerHeight, bottomSpacerHeight } = useMemo(() => {
    const visibleCount = Math.ceil(TABLE_HEIGHT / ROW_HEIGHT);
    const firstVisible = Math.floor(scrollTop / ROW_HEIGHT);
    const start = Math.max(0, firstVisible - OVERSCAN);
    const end = Math.min(rows.length, firstVisible + visibleCount + OVERSCAN);
    return {
      startIndex: start,
      endIndex: end,
      topSpacerHeight: start * ROW_HEIGHT,
      bottomSpacerHeight: Math.max(0, (rows.length - end) * ROW_HEIGHT),
    };
  }, [scrollTop, rows.length]);

  const windowRows = useMemo(
    () =>
      rows.slice(startIndex, endIndex).map((row, offset) => ({ row, index: startIndex + offset })),
    [rows, startIndex, endIndex],
  );

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  };

  if (dataset.columns.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" role="status">
        No columns were produced. Select at least one feature and rebuild.
      </Typography>
    );
  }

  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" role="status">
        The dataset has no rows. Every row was dropped as warmup — widen the date range or reduce
        the largest period.
      </Typography>
    );
  }

  const columnCount = dataset.columns.length + 1; // + timestamp

  return (
    <Stack spacing={1}>
      <TableContainer
        ref={containerRef}
        component={Paper}
        variant="outlined"
        onScroll={handleScroll}
        sx={{ maxHeight: TABLE_HEIGHT, overflowX: 'auto', overflowY: 'auto' }}
      >
        <Table size="small" stickyHeader aria-label="Feature dataset preview">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>Timestamp</TableCell>
              {dataset.columns.map((column) => (
                <TableCell
                  key={column.name}
                  align="right"
                  sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}
                >
                  <Stack
                    direction="row"
                    spacing={0.25}
                    alignItems="center"
                    justifyContent="flex-end"
                  >
                    <Box component="span">{column.name}</Box>
                    <InfoTooltip
                      label={column.name}
                      sections={[
                        { heading: 'Description', body: column.description || column.label },
                        { heading: 'Type', body: column.dtype },
                      ]}
                    />
                  </Stack>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {topSpacerHeight > 0 ? (
              <TableRow style={{ height: topSpacerHeight }} aria-hidden>
                <TableCell colSpan={columnCount} sx={{ p: 0, border: 'none' }} />
              </TableRow>
            ) : null}
            {windowRows.map(({ row, index }) => (
              <TableRow key={timestamps[index] ?? index} hover style={{ height: ROW_HEIGHT }}>
                <TableCell sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                  {timestamps[index]}
                </TableCell>
                {row.map((value, columnIndex) => (
                  <TableCell
                    key={dataset.columns[columnIndex]?.name ?? columnIndex}
                    align="right"
                    sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
                  >
                    {formatCell(value)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            {bottomSpacerHeight > 0 ? (
              <TableRow style={{ height: bottomSpacerHeight }} aria-hidden>
                <TableCell colSpan={columnCount} sx={{ p: 0, border: 'none' }} />
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      {dataset.meta.truncated ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color="info" variant="outlined" label="Preview" />
          <Typography variant="caption" color="text.secondary">
            Showing {dataset.meta.row_count.toLocaleString()} of{' '}
            {dataset.meta.total_rows.toLocaleString()} rows. Exports always contain the full
            dataset.
          </Typography>
        </Stack>
      ) : null}
    </Stack>
  );
}

export const DatasetPreviewTable = memo(DatasetPreviewTableInner);
