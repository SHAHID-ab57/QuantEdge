'use client';

import FilterAltOffIcon from '@mui/icons-material/FilterAltOff';
import SearchIcon from '@mui/icons-material/Search';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { MARKET_TYPE_OPTIONS } from '../hooks/use-market-url-state';

export interface MarketsToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  type: string;
  status: string;
  exchange: string;
  exchanges: string[];
  onFilterChange: (key: 'type' | 'status' | 'exchange', value: string) => void;
  hasFilters: boolean;
  onClearFilters: () => void;
}

export function MarketsToolbar({
  search,
  onSearchChange,
  type,
  status,
  exchange,
  exchanges,
  onFilterChange,
  hasFilters,
  onClearFilters,
}: MarketsToolbarProps) {
  return (
    <Box
      component="form"
      role="search"
      aria-label="Filter markets"
      onSubmit={(event) => event.preventDefault()}
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}
    >
      <TextField
        label="Search symbols"
        placeholder="e.g. BTCUSD"
        size="small"
        value={search}
        onChange={(event) => onSearchChange(event.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
        sx={{ flexGrow: 1, minWidth: 200, maxWidth: 320 }}
      />
      <TextField
        select
        label="Market Type"
        size="small"
        value={type}
        onChange={(event) => onFilterChange('type', event.target.value)}
        slotProps={{ select: { 'aria-label': 'Filter by market type' } }}
        sx={{ minWidth: 150 }}
      >
        <MenuItem value="">All</MenuItem>
        {MARKET_TYPE_OPTIONS.map((option) => (
          <MenuItem key={option} value={option}>
            {option}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Status"
        size="small"
        value={status}
        onChange={(event) => onFilterChange('status', event.target.value)}
        slotProps={{ select: { 'aria-label': 'Filter by status' } }}
        sx={{ minWidth: 130 }}
      >
        <MenuItem value="">All</MenuItem>
        <MenuItem value="active">Active</MenuItem>
        <MenuItem value="inactive">Inactive</MenuItem>
      </TextField>
      <TextField
        select
        label="Exchange"
        size="small"
        value={exchange}
        onChange={(event) => onFilterChange('exchange', event.target.value)}
        slotProps={{ select: { 'aria-label': 'Filter by exchange' } }}
        sx={{ minWidth: 180, maxWidth: 260 }}
      >
        <MenuItem value="">All</MenuItem>
        {exchanges.map((name) => (
          <MenuItem key={name} value={name}>
            {name}
          </MenuItem>
        ))}
      </TextField>
      {hasFilters ? (
        <Button
          size="small"
          onClick={onClearFilters}
          startIcon={<FilterAltOffIcon fontSize="small" />}
        >
          Clear filters
        </Button>
      ) : null}
    </Box>
  );
}
