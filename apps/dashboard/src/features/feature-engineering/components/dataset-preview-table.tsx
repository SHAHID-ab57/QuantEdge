'use client';

import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { memo, useEffect, useMemo, useRef, useState, type MouseEvent, type UIEvent } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { isSplitLabel, SPLIT_COLORS, type SplitLabel } from '@/lib/split-label';
import type { FeatureCell, FeatureColumn } from '@/types/api/features';
import { ColumnStatsPopover } from './column-stats-popover';
import { isNumericDtype } from '../lib/column-stats';
import { formatCell } from '../lib/feature-selection';

/**
 * The minimal shape this table actually reads. Deliberately looser than
 * `FeatureDataset` so the ML Dataset Builder's `MLDatasetResponse` — a
 * different, richer wire type with its own `meta` shape — can be previewed
 * by this same component without a structural cast, matching this
 * codebase's existing preference to reuse a rendering component rather
 * than fork it for a second, near-identical dataset type.
 */
export interface PreviewableDataset {
  columns: FeatureColumn[];
  timestamps: string[];
  rows: FeatureCell[][];
  meta: { truncated: boolean; row_count: number; total_rows: number };
}

export interface DatasetPreviewTableProps {
  dataset: PreviewableDataset;
  /** Rows to render; the response may already be truncated server-side. */
  maxRows?: number;
  /**
   * Column names that are prediction labels rather than model inputs — the
   * ML Dataset Builder's target columns. Highlighted in the header so a
   * researcher can tell inputs (X) from labels (y) at a glance.
   */
  targetColumns?: readonly string[];
  /**
   * Per-row split label ("train"/"validation"/"test"), parallel to
   * `dataset.rows`/`dataset.timestamps`. Rendered as a trailing "Split"
   * column when present — the ML Dataset Builder's single flat export
   * carries exactly this column, so the preview mirrors it.
   */
  splitLabels?: readonly string[];
}

/** Fixed row height (px) the virtualization math is built on — every row renders identically. */
const ROW_HEIGHT = 33;
/** The scrollable area's height; also what bounds how many rows are ever mounted at once. */
const TABLE_HEIGHT = 460;
/** Extra rows rendered beyond the visible window on each side, so a fast scroll never flashes blank space. */
const OVERSCAN = 8;
/** Width reserved for the sticky first (Timestamp) column, so body cells can offset under it consistently. */
const TIMESTAMP_COLUMN_WIDTH = 190;

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
 *
 * The Timestamp column stays **sticky** while scrolling horizontally
 * through a wide feature matrix, since it is the one column every other
 * value is read relative to. A **column search** box and a **column
 * visibility** menu let a researcher narrow a wide matrix down to the
 * handful of columns they're actually comparing, without losing any data —
 * both are display-only and never affect `rows`/`timestamps` themselves,
 * so an export is always the complete matrix regardless of what's
 * currently hidden here.
 */
function DatasetPreviewTableInner({
  dataset,
  maxRows,
  targetColumns,
  splitLabels,
}: DatasetPreviewTableProps) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const targetColumnSet = useMemo(() => new Set(targetColumns ?? []), [targetColumns]);

  const [columnSearch, setColumnSearch] = useState('');
  const [hiddenColumns, setHiddenColumns] = useState<ReadonlySet<string>>(new Set());
  const [columnMenuAnchor, setColumnMenuAnchor] = useState<HTMLElement | null>(null);

  // A fresh build's column list should never inherit a stale hidden-column
  // choice from a previous, differently-shaped dataset.
  const columnKey = dataset.columns.map((column) => column.name).join('|');
  useEffect(() => {
    setHiddenColumns(new Set());
  }, [columnKey]);

  const columnIndexByName = useMemo(
    () => new Map(dataset.columns.map((column, index) => [column.name, index])),
    [dataset.columns],
  );

  const visibleColumns = useMemo(() => {
    const search = columnSearch.trim().toLowerCase();
    return dataset.columns.filter(
      (column) =>
        !hiddenColumns.has(column.name) &&
        (search === '' || column.name.toLowerCase().includes(search)),
    );
  }, [dataset.columns, hiddenColumns, columnSearch]);

  const rows = useMemo(
    () => (maxRows === undefined ? dataset.rows : dataset.rows.slice(0, maxRows)),
    [dataset.rows, maxRows],
  );
  const timestamps = useMemo(
    () => (maxRows === undefined ? dataset.timestamps : dataset.timestamps.slice(0, maxRows)),
    [dataset.timestamps, maxRows],
  );
  const splits = useMemo(() => {
    if (splitLabels === undefined) {
      return undefined;
    }
    return maxRows === undefined ? splitLabels : splitLabels.slice(0, maxRows);
  }, [splitLabels, maxRows]);

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

  const toggleColumnVisibility = (name: string) => {
    setHiddenColumns((current) => {
      const next = new Set(current);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
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

  const columnCount = visibleColumns.length + 1 + (splits ? 1 : 0); // + timestamp (+ split)

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          placeholder="Search columns…"
          value={columnSearch}
          onChange={(event) => setColumnSearch(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Search columns' } }}
          sx={{ minWidth: 200 }}
        />
        <IconButton
          size="small"
          aria-label="Toggle column visibility"
          onClick={(event: MouseEvent<HTMLElement>) => setColumnMenuAnchor(event.currentTarget)}
        >
          <ViewColumnIcon fontSize="small" />
        </IconButton>
        <Menu
          anchorEl={columnMenuAnchor}
          open={Boolean(columnMenuAnchor)}
          onClose={() => setColumnMenuAnchor(null)}
        >
          {dataset.columns.map((column) => (
            <MenuItem
              key={column.name}
              dense
              onClick={() => toggleColumnVisibility(column.name)}
              aria-label={`Toggle ${column.name} visibility`}
            >
              <Checkbox size="small" checked={!hiddenColumns.has(column.name)} sx={{ p: 0.5 }} />
              <ListItemText primary={column.name} />
            </MenuItem>
          ))}
        </Menu>
        {hiddenColumns.size > 0 ? (
          <Typography variant="caption" color="text.secondary">
            {hiddenColumns.size} column{hiddenColumns.size === 1 ? '' : 's'} hidden
          </Typography>
        ) : null}
      </Stack>

      {visibleColumns.length === 0 ? (
        <Typography variant="body2" color="text.secondary" role="status">
          No columns match “{columnSearch}”, or every matching column is hidden.
        </Typography>
      ) : (
        <TableContainer
          ref={containerRef}
          component={Paper}
          variant="outlined"
          onScroll={handleScroll}
          sx={{
            maxHeight: TABLE_HEIGHT,
            overflowX: 'auto',
            overflowY: 'auto',
            // Virtualization renders spacer rows whose height changes on every
            // scroll-driven re-render. Without this, the browser's native
            // "scroll anchoring" (which auto-corrects scrollTop whenever
            // content above the viewport shifts) fights our own scrollTop
            // state in a feedback loop — each correction fires another
            // `scroll` event, which sets state again, which resizes the
            // spacers again, forever ("Maximum update depth exceeded").
            // Disabling it here is the standard fix for this exact class of
            // bug in any spacer-based virtualized list.
            overflowAnchor: 'none',
          }}
        >
          <Table size="small" stickyHeader aria-label="Feature dataset preview">
            <TableHead>
              <TableRow>
                <TableCell
                  sx={{
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                    position: 'sticky',
                    left: 0,
                    zIndex: 3,
                    bgcolor: 'background.paper',
                    minWidth: TIMESTAMP_COLUMN_WIDTH,
                  }}
                >
                  Timestamp
                </TableCell>
                {visibleColumns.map((column) => {
                  const isTarget = targetColumnSet.has(column.name);
                  const columnIndex = columnIndexByName.get(column.name) ?? -1;
                  return (
                    <TableCell
                      key={column.name}
                      align="right"
                      sx={{
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        bgcolor: isTarget ? 'action.selected' : undefined,
                      }}
                    >
                      <Stack
                        direction="row"
                        spacing={0.25}
                        alignItems="center"
                        justifyContent="flex-end"
                      >
                        {isTarget ? <Chip size="small" label="target" sx={{ height: 18 }} /> : null}
                        <Box component="span">{column.name}</Box>
                        {isNumericDtype(column.dtype) ? (
                          <ColumnStatsPopover
                            columnName={column.name}
                            values={rows.map((row) => row[columnIndex] ?? null)}
                            isPreviewSubset={
                              dataset.meta.truncated || rows.length !== dataset.rows.length
                            }
                          />
                        ) : null}
                        <InfoTooltip
                          label={column.name}
                          sections={[
                            { heading: 'Description', body: column.description || column.label },
                            { heading: 'Type', body: column.dtype },
                            ...(isTarget
                              ? [
                                  {
                                    heading: 'Role',
                                    body: 'Prediction target (label), not a model input.',
                                  },
                                ]
                              : []),
                          ]}
                        />
                      </Stack>
                    </TableCell>
                  );
                })}
                {splits ? (
                  <TableCell align="center" sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                    Split
                  </TableCell>
                ) : null}
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
                  <TableCell
                    sx={{
                      whiteSpace: 'nowrap',
                      fontVariantNumeric: 'tabular-nums',
                      position: 'sticky',
                      left: 0,
                      zIndex: 1,
                      bgcolor: 'background.paper',
                      minWidth: TIMESTAMP_COLUMN_WIDTH,
                    }}
                  >
                    {timestamps[index]}
                  </TableCell>
                  {visibleColumns.map((column) => {
                    const columnIndex = columnIndexByName.get(column.name) ?? -1;
                    const isTarget = targetColumnSet.has(column.name);
                    return (
                      <TableCell
                        key={column.name}
                        align="right"
                        sx={{
                          fontVariantNumeric: 'tabular-nums',
                          whiteSpace: 'nowrap',
                          bgcolor: isTarget ? 'action.hover' : undefined,
                        }}
                      >
                        {formatCell(row[columnIndex] ?? null)}
                      </TableCell>
                    );
                  })}
                  {splits ? (
                    <TableCell align="center">
                      <Chip
                        size="small"
                        label={splits[index]}
                        color={
                          isSplitLabel(splits[index] ?? '')
                            ? SPLIT_COLORS[splits[index] as SplitLabel]
                            : 'default'
                        }
                        variant="outlined"
                      />
                    </TableCell>
                  ) : null}
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
      )}

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
