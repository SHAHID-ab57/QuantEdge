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
import Typography from '@mui/material/Typography';
import type { CandlePageResult } from '../hooks/use-history-data';
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
  data: CandlePageResult | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
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

export function CandlesTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
  onLimitChange,
}: CandlesTableProps) {
  const candles = data?.page.items ?? [];
  const total = data?.page.pagination.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 560 }}>
        <Table stickyHeader aria-label="Candles table" size="small">
          <TableHead>
            <TableRow>
              {COLUMNS.map((column) => (
                <TableCell key={column.key} align={column.align}>
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows rows={Math.min(limit, 20)} />
            ) : (
              candles.map((candle) => (
                <TableRow key={`${candle.open_time}-${candle.close_time}`} hover>
                  <TableCell>{formatTime(candle.open_time)}</TableCell>
                  <TableCell align="right">{formatDecimal(candle.open)}</TableCell>
                  <TableCell align="right">{formatDecimal(candle.high)}</TableCell>
                  <TableCell align="right">{formatDecimal(candle.low)}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight={600}>
                      {formatDecimal(candle.close)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{formatDecimal(candle.volume)}</TableCell>
                </TableRow>
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
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
        <FormControl size="small" sx={{ mr: 1, minWidth: 80 }}>
          <Select
            value={limit}
            onChange={(event) => onLimitChange(Number(event.target.value))}
            aria-label="Rows per page"
          >
            {[100, 250, 500, 1000].map((option) => (
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
