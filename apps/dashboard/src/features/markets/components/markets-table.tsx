'use client';

import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import FormControl from '@mui/material/FormControl';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import SearchOffIcon from '@mui/icons-material/SearchOff';
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
import { alpha, useTheme } from '@mui/material/styles';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, type KeyboardEvent } from 'react';
import type { Market } from '@/types/api/market';
import { prefetchMarketDetail } from '../hooks/use-markets-data';
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
  const queryClient = useQueryClient();
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (hoverTimer.current) {
        clearTimeout(hoverTimer.current);
      }
    },
    [],
  );

  const handleRowEnter = (symbol: string) => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
    }
    hoverTimer.current = setTimeout(() => prefetchMarketDetail(queryClient, symbol), 250);
  };

  const handleRowLeave = () => {
    if (hoverTimer.current) {
      clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
    }
  };

  const handleRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, symbol: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelectRow(symbol);
    }
  };

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
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                    borderBottomColor: 'divider',
                    '&:hover': {
                      backgroundColor: alpha(theme.palette.action.hover, 0.35),
                    },
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
              <TableCell
                sx={{
                  display: compact ? 'none' : undefined,
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                  borderBottomColor: 'divider',
                }}
              >
                Status
              </TableCell>
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
                  onMouseEnter={() => handleRowEnter(market.symbol)}
                  onMouseLeave={handleRowLeave}
                  onFocus={() => handleRowEnter(market.symbol)}
                  onKeyDown={(event) => handleRowKeyDown(event, market.symbol)}
                  tabIndex={0}
                  aria-selected={isSelected}
                  sx={{
                    cursor: 'pointer',
                    transition: 'background-color 120ms ease',
                    '&.Mui-selected': {
                      backgroundColor: alpha(theme.palette.primary.main, 0.08),
                      '&:hover': {
                        backgroundColor: alpha(theme.palette.primary.main, 0.14),
                      },
                    },
                    '&:focus-visible': {
                      outline: '2px solid',
                      outlineColor: 'primary.main',
                      outlineOffset: -2,
                    },
                  }}
                >
                  <TableCell
                    component="th"
                    scope="row"
                    sx={
                      isSelected
                        ? { boxShadow: `inset 3px 0 0 ${theme.palette.primary.main}` }
                        : undefined
                    }
                  >
                    <Typography variant="body2" fontWeight={700}>
                      {market.symbol}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {market.exchange}
                    </Typography>
                  </TableCell>
                  <TableCell sx={{ display: compact ? 'none' : undefined }}>
                    {market.base_asset}
                  </TableCell>
                  <TableCell sx={{ display: compact ? 'none' : undefined }}>
                    {market.quote_asset}
                  </TableCell>
                  <TableCell sx={{ textTransform: 'capitalize' }}>{market.market_type}</TableCell>
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
                    <SearchOffIcon color="disabled" sx={{ fontSize: 40 }} aria-hidden />
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
      <Divider />
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', px: 1 }}>
        <FormControl size="small" sx={{ mr: 1, minWidth: 80 }}>
          <Select
            value={size}
            onChange={(event) => onSizeChange(Number(event.target.value))}
            aria-label="Rows per page"
            inputProps={{ 'aria-label': 'Rows per page' }}
            sx={{ height: 32 }}
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
          sx={{
            '& .MuiTablePagination-toolbar': {
              minHeight: 52,
              pl: 1,
            },
          }}
        />
      </Box>
    </Paper>
  );
}
