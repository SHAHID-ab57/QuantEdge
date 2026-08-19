'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import FormControl from '@mui/material/FormControl';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Select from '@mui/material/Select';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import type { Market } from '@/types/api/market';
import { PAGE_SIZE_OPTIONS, type SortDir, type SortKey } from '../hooks/use-market-url-state';

export interface ColumnMeta {
  key: SortKey;
  label: string;
}

const SORTABLE_COLUMNS: ColumnMeta[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'exchange', label: 'Exchange' },
  { key: 'base_asset', label: 'Base Asset' },
  { key: 'quote_asset', label: 'Quote Asset' },
  { key: 'market_type', label: 'Market Type' },
];

interface MarketsTableProps {
  rows: Market[];
  total: number;
  sort: SortKey;
  dir: SortDir;
  onSort: (key: SortKey) => void;
  page: number;
  size: number;
  onPageChange: (page: number) => void;
  onSizeChange: (size: number) => void;
  selectedSymbol: string | null;
  onSelectRow: (symbol: string) => void;
}

function getAriaSort(
  key: SortKey,
  sort: SortKey,
  dir: SortDir,
): 'ascending' | 'descending' | undefined {
  if (key !== sort) {
    return undefined;
  }
  return dir === 'asc' ? 'ascending' : 'descending';
}

export function MarketsTable({
  rows,
  total,
  sort,
  dir,
  onSort,
  page,
  size,
  onPageChange,
  onSizeChange,
  selectedSymbol,
  onSelectRow,
}: MarketsTableProps) {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('md'));

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 560 }}>
        <Table stickyHeader aria-label="Markets table" size={compact ? 'small' : 'medium'}>
          <TableHead>
            <TableRow>
              {SORTABLE_COLUMNS.map((column) => (
                <TableCell
                  key={column.key}
                  aria-sort={getAriaSort(column.key, sort, dir)}
                  sx={{
                    display:
                      compact && column.key !== 'symbol' && column.key !== 'exchange'
                        ? 'none'
                        : undefined,
                  }}
                >
                  <TableSortLabel
                    active={sort === column.key}
                    direction={sort === column.key ? dir : 'asc'}
                    onClick={() => onSort(column.key)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
              <TableCell sx={{ display: compact ? 'none' : undefined }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((market) => {
              const isSelected = market.symbol === selectedSymbol;
              return (
                <TableRow
                  key={market.id}
                  hover
                  selected={isSelected}
                  onClick={() => onSelectRow(market.symbol)}
                  sx={{ cursor: 'pointer' }}
                  aria-selected={isSelected}
                >
                  <TableCell component="th" scope="row">
                    <Typography variant="body2" fontWeight={600}>
                      {market.symbol}
                    </Typography>
                  </TableCell>
                  <TableCell>{market.exchange}</TableCell>
                  <TableCell sx={{ display: compact ? 'none' : undefined }}>
                    {market.base_asset}
                  </TableCell>
                  <TableCell sx={{ display: compact ? 'none' : undefined }}>
                    {market.quote_asset}
                  </TableCell>
                  <TableCell>{market.market_type}</TableCell>
                  <TableCell sx={{ display: compact ? 'none' : undefined }}>
                    <Chip
                      label={market.is_active ? 'Active' : 'Inactive'}
                      color={market.is_active ? 'success' : 'default'}
                      size="small"
                      variant="outlined"
                    />
                  </TableCell>
                </TableRow>
              );
            })}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                  <Stack
                    spacing={1}
                    alignItems="center"
                    role="status"
                    aria-label="No markets match"
                  >
                    <Typography variant="body1" color="text.secondary">
                      No markets match the current filters.
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Try adjusting or clearing the search and filters.
                    </Typography>
                  </Stack>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
        <FormControl size="small" sx={{ mr: 1, minWidth: 80 }}>
          <Select
            value={size}
            onChange={(event) => onSizeChange(Number(event.target.value))}
            aria-label="Rows per page"
            inputProps={{ 'aria-label': 'Rows per page' }}
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
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
          rowsPerPage={size}
          rowsPerPageOptions={[]}
          labelRowsPerPage=""
        />
      </Box>
    </Paper>
  );
}
