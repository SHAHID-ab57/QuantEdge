'use client';

import SearchIcon from '@mui/icons-material/Search';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { statusLabel } from '../lib/experiment-status';

export interface ExperimentFiltersValue {
  search: string;
  status: string;
  tag: string;
}

export interface ExperimentFiltersBarProps {
  value: ExperimentFiltersValue;
  onChange: (value: ExperimentFiltersValue) => void;
  statuses: readonly string[];
}

const ALL_STATUSES = '__all__';

/**
 * Search-by-name/notes plus a status filter and an exact-tag filter — the
 * "Search"/"Filter" half of the list page, backed directly by the backend's
 * own `q`/`status`/`tag` query parameters (`GET /experiments`). Sorting
 * lives on the table's own column headers instead of here, since a sort
 * column is naturally a property of the table being sorted, not a
 * free-standing filter.
 */
export function ExperimentFiltersBar({ value, onChange, statuses }: ExperimentFiltersBarProps) {
  const set = <K extends keyof ExperimentFiltersValue>(key: K, next: ExperimentFiltersValue[K]) => {
    onChange({ ...value, [key]: next });
  };

  return (
    <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
      <TextField
        size="small"
        placeholder="Search name or notes…"
        value={value.search}
        onChange={(event) => set('search', event.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
          htmlInput: { 'aria-label': 'Search experiments' },
        }}
        sx={{ minWidth: 240, flexGrow: 1 }}
      />
      <TextField
        select
        size="small"
        label="Status"
        value={value.status || ALL_STATUSES}
        onChange={(event) =>
          set('status', event.target.value === ALL_STATUSES ? '' : event.target.value)
        }
        sx={{ minWidth: 160 }}
      >
        <MenuItem value={ALL_STATUSES}>All statuses</MenuItem>
        {statuses.map((status) => (
          <MenuItem key={status} value={status}>
            {statusLabel(status)}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        size="small"
        label="Tag"
        placeholder="e.g. baseline"
        value={value.tag}
        onChange={(event) => set('tag', event.target.value)}
        slotProps={{ htmlInput: { 'aria-label': 'Filter by tag' } }}
        sx={{ minWidth: 160 }}
      />
    </Stack>
  );
}
