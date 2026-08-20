'use client';

import Box from '@mui/material/Box';
import FormControl from '@mui/material/FormControl';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Select from '@mui/material/Select';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Typography from '@mui/material/Typography';
import { memo, useCallback, useEffect, useRef, useState } from 'react';
import type { CandlePage } from '@/types/api/market';
import {
  HISTORY_LIMIT_OPTIONS,
  type CandleSortColumn,
  type CandleSortDirection,
} from '../hooks/use-history-data';
import { formatDecimal, formatTime } from '../lib/format';

const COLUMNS = [
  { key: 'open_time', label: 'Open Time', align: 'left' as const },
  { key: 'open', label: 'Open', align: 'right' as const },
  { key: 'high', label: 'High', align: 'right' as const },
  { key: 'low', label: 'Low', align: 'right' as const },
  { key: 'close', label: 'Close', align: 'right' as const },
  { key: 'volume', label: 'Volume', align: 'right' as const },
];

interface CandlesTableProps {
  data: CandlePage | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  sort: CandleSortColumn;
  dir: CandleSortDirection;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
  onSortChange: (sort: CandleSortColumn, dir: CandleSortDirection) => void;
}

function LoadingRows({ rows }: { rows: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={COLUMNS.length}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

async function copyToClipboard(value: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

interface CandleRowProps {
  openTime: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  selected: boolean;
  onCopy: (openTime: string, value: string) => void;
}

const CandleRow = memo(function CandleRow({
  openTime,
  open,
  high,
  low,
  close,
  volume,
  selected,
  onCopy,
}: CandleRowProps) {
  const cellSx = { cursor: 'pointer' };
  return (
    <TableRow hover selected={selected}>
      <TableCell sx={cellSx} onClick={() => onCopy(openTime, openTime)} title={`UTC: ${openTime}`}>
        {formatTime(openTime)}
      </TableCell>
      <TableCell align="right" sx={cellSx} onClick={() => onCopy(openTime, open)}>
        {formatDecimal(open)}
      </TableCell>
      <TableCell align="right" sx={cellSx} onClick={() => onCopy(openTime, high)}>
        {formatDecimal(high)}
      </TableCell>
      <TableCell align="right" sx={cellSx} onClick={() => onCopy(openTime, low)}>
        {formatDecimal(low)}
      </TableCell>
      <TableCell align="right" sx={cellSx} onClick={() => onCopy(openTime, close)}>
        <Typography variant="body2" fontWeight={600}>
          {formatDecimal(close)}
        </Typography>
      </TableCell>
      <TableCell align="right" sx={cellSx} onClick={() => onCopy(openTime, volume)}>
        {formatDecimal(volume)}
      </TableCell>
    </TableRow>
  );
});

export function CandlesTable({
  data,
  isLoading,
  page,
  limit,
  sort,
  dir,
  onPageChange,
  onLimitChange,
  onSortChange,
}: CandlesTableProps) {
  const candles = data?.items ?? [];
  const total = data?.pagination.total ?? 0;
  const [selected, setSelected] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimer.current) {
        clearTimeout(copyTimer.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async (openTime: string, value: string) => {
    setSelected(openTime);
    if (await copyToClipboard(value)) {
      setCopied(`${formatTime(openTime)} · ${value}`);
      if (copyTimer.current) {
        clearTimeout(copyTimer.current);
      }
      copyTimer.current = setTimeout(() => setCopied(null), 1600);
    }
  }, []);

  const handleSort = useCallback(
    (key: CandleSortColumn) => {
      if (key === sort) {
        onSortChange(key, dir === 'asc' ? 'desc' : 'asc');
      } else {
        onSortChange(key, 'asc');
      }
    },
    [dir, onSortChange, sort],
  );

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 560 }}>
        <Table stickyHeader aria-label="Candles table" size="small">
          <TableHead>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableCell
                  key={column.key}
                  align={column.align}
                  sortDirection={sort === column.key ? dir : false}
                >
                  <TableSortLabel
                    active={sort === column.key}
                    direction={sort === column.key ? dir : 'asc'}
                    onClick={() => handleSort(column.key as CandleSortColumn)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows rows={Math.min(limit, 20)} />
            ) : (
              candles.map((candle) => (
                <CandleRow
                  key={candle.open_time}
                  openTime={candle.open_time}
                  open={candle.open}
                  high={candle.high}
                  low={candle.low}
                  close={candle.close}
                  volume={candle.volume}
                  selected={selected === candle.open_time}
                  onCopy={handleCopy}
                />
              ))
            )}
            {!isLoading && candles.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMNS.length} align="center" sx={{ py: 5 }}>
                  <Typography
                    variant="body1"
                    color="text.secondary"
                    role="status"
                    aria-label="No candles found"
                  >
                    No candles in this range.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      {copied ? (
        <Box sx={{ px: 2, pt: 1 }}>
          <Typography
            variant="caption"
            color="text.secondary"
            role="status"
            aria-label="Copied value"
          >
            Copied {copied} to the clipboard.
          </Typography>
        </Box>
      ) : null}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
        <FormControl size="small" sx={{ mr: 1, minWidth: 80 }}>
          <Select
            value={limit}
            onChange={(event) => onLimitChange(Number(event.target.value))}
            aria-label="Rows per page"
          >
            {HISTORY_LIMIT_OPTIONS.map((option) => (
              <MenuItem key={option} value={option}>
                {option} / page
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TablePagination
          component="div"
          count={total}
          page={page - 1}
          onPageChange={(_, nextPage) => onPageChange(nextPage + 1)}
          rowsPerPage={limit}
          rowsPerPageOptions={[]}
          labelRowsPerPage=""
        />
      </Box>
    </Paper>
  );
}
