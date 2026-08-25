'use client';

import CheckBoxIcon from '@mui/icons-material/CheckBox';
import CheckBoxOutlineBlankIcon from '@mui/icons-material/CheckBoxOutlineBlank';
import HistoryIcon from '@mui/icons-material/History';
import Autocomplete, { createFilterOptions } from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMemo } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import type { FeatureSelection } from '@/features/feature-engineering/lib/feature-selection';
import type { Feature } from '@/types/api/features';
import { useRecentColumnsStore } from '../store/use-recent-columns-store';
import {
  REQUIRED_COLUMN_CATEGORY_ORDER,
  resolveRequiredColumnOptions,
  type RequiredColumnOption,
} from '../lib/resolve-required-columns';

export interface RequiredColumnsSelectorProps {
  features: readonly Feature[];
  selections: readonly FeatureSelection[];
  value: readonly string[];
  onChange: (next: string[]) => void;
}

const CHECKBOX_UNCHECKED = <CheckBoxOutlineBlankIcon fontSize="small" />;
const CHECKBOX_CHECKED = <CheckBoxIcon fontSize="small" />;

const filterOptions = createFilterOptions<RequiredColumnOption>({
  stringify: (option) => `${option.name} ${option.featureLabel} ${option.category}`,
});

const CATEGORY_RANK = new Map(
  REQUIRED_COLUMN_CATEGORY_ORDER.map((category, index) => [category, index]),
);

function sortByCategoryOrder(a: string, b: string): number {
  const rankA = CATEGORY_RANK.get(a) ?? REQUIRED_COLUMN_CATEGORY_ORDER.length;
  const rankB = CATEGORY_RANK.get(b) ?? REQUIRED_COLUMN_CATEGORY_ORDER.length;
  return rankA !== rankB ? rankA - rankB : a.localeCompare(b);
}

/**
 * A searchable, multi-select, checkbox-driven replacement for the free-
 * text "Required Columns" input — the single change this whole module's
 * usability pass makes to how a required column is *chosen*, without
 * touching what gets sent: the value is still a plain `string[]`, exactly
 * what `required_columns` on `DatasetValidationRequest` always accepted.
 *
 * Options come from `resolveRequiredColumnOptions` (Feature Registry
 * metadata resolved against the current selection), grouped into the five
 * fixed UI buckets and rendered via MUI's `Autocomplete` — the same
 * component `DatasetForm`'s Market field already uses, so this follows the
 * existing design system rather than introducing a new selection widget.
 * `freeSolo` stays enabled so a researcher can still type an arbitrary
 * column name the resolver doesn't (yet) know about — deliberately
 * preserving the original field's flexibility, since a column belonging to
 * a feature that isn't currently selected is exactly the case a validation
 * gate is useful for catching.
 */
export function RequiredColumnsSelector({
  features,
  selections,
  value,
  onChange,
}: RequiredColumnsSelectorProps) {
  const options = useMemo(() => {
    // MUI Autocomplete's `groupBy` requires options pre-sorted by the same
    // key, or the same group heading is rendered more than once.
    return [...resolveRequiredColumnOptions(features, selections)].sort((a, b) => {
      const byCategory = sortByCategoryOrder(a.category, b.category);
      return byCategory !== 0 ? byCategory : a.name.localeCompare(b.name);
    });
  }, [features, selections]);
  const recent = useRecentColumnsStore((state) => state.recent);

  const selectedOptions = useMemo<RequiredColumnOption[]>(() => {
    const byName = new Map(options.map((option) => [option.name, option]));
    return value.map(
      (name) => byName.get(name) ?? { name, feature: '', featureLabel: '', category: 'Other' },
    );
  }, [value, options]);

  const recentNames = useMemo(
    () => recent.filter((name) => !value.includes(name)),
    [recent, value],
  );

  const commit = (names: readonly string[]) => {
    const deduped = Array.from(new Set(names));
    onChange(deduped);
  };

  const addColumn = (name: string) => {
    if (value.includes(name)) {
      return;
    }
    useRecentColumnsStore.getState().recordUsed(name);
    commit([...value, name]);
  };

  const selectAll = () => {
    commit(options.map((option) => option.name));
  };

  const clearAll = () => {
    commit([]);
  };

  return (
    <Stack spacing={0.75}>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Typography variant="body2" component="span">
          Required columns
        </Typography>
        <InfoTooltip
          label="Required columns"
          sections={[
            {
              heading: 'Purpose',
              body: 'Column names that must exist in the built dataset, beyond what the selected features already imply — a stricter, explicit contract for a downstream pipeline.',
            },
            {
              heading: 'Expected values',
              body: 'Column names as they would appear in the built dataset (e.g. close, sma_20). Pick from the searchable list, grouped by category, or type a name that is not in the list yet.',
            },
            {
              heading: 'Validation rules',
              body: 'Any named column missing from the built dataset fails validation with a missing_required_column error.',
            },
            {
              heading: 'Example',
              body: 'Requiring sma_20 without selecting sma at period=20 fails on purpose — proving the check works.',
            },
          ]}
        />
        <Typography variant="caption" color="text.secondary">
          ({value.length} selected)
        </Typography>
      </Stack>

      <Autocomplete
        multiple
        freeSolo
        disableCloseOnSelect
        size="small"
        options={options}
        value={selectedOptions}
        groupBy={(option) => option.category}
        getOptionLabel={(option) => (typeof option === 'string' ? option : option.name)}
        isOptionEqualToValue={(option, selected) => option.name === selected.name}
        filterOptions={filterOptions}
        onChange={(_, newValue) => {
          commit(newValue.map((entry) => (typeof entry === 'string' ? entry : entry.name)));
        }}
        renderOption={(props, option, { selected }) => {
          const { key, ...rest } = props as typeof props & { key: string };
          return (
            <li key={key} {...rest}>
              <Checkbox
                icon={CHECKBOX_UNCHECKED}
                checkedIcon={CHECKBOX_CHECKED}
                checked={selected}
                size="small"
                sx={{ mr: 1 }}
              />
              {option.name}
            </li>
          );
        }}
        renderInput={(params) => (
          <TextField
            {...params}
            placeholder={value.length > 0 ? 'Add another column…' : 'Search columns…'}
            slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Required columns' } }}
          />
        )}
        sx={{ maxWidth: 480 }}
      />

      <Stack direction="row" spacing={1}>
        <Button size="small" onClick={selectAll} disabled={options.length === 0}>
          Select All
        </Button>
        <Button size="small" onClick={clearAll} disabled={value.length === 0}>
          Clear All
        </Button>
      </Stack>

      {recentNames.length > 0 ? (
        <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <HistoryIcon fontSize="small" sx={{ color: 'text.secondary' }} aria-hidden />
          <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
            Recently used:
          </Typography>
          {recentNames.map((name) => (
            <Chip
              key={name}
              size="small"
              variant="outlined"
              label={name}
              onClick={() => addColumn(name)}
              aria-label={`Add ${name} (recently used column)`}
            />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
