'use client';

import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HistoryIcon from '@mui/icons-material/History';
import SearchIcon from '@mui/icons-material/Search';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import TuneIcon from '@mui/icons-material/Tune';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { ParameterForm } from '@/features/indicators/components/parameter-form';
import { validateValues } from '@/features/indicators/lib/parameter-values';
import { matchesCatalogSearch } from '@/lib/search-catalog';
import type { Feature } from '@/types/api/features';
import { useFavoriteFeaturesStore } from '../store/use-favorite-features-store';
import { useRecentFeaturesStore } from '../store/use-recent-features-store';
import {
  groupFeaturesByCategory,
  isSelected,
  paramSummary,
  type FeatureSelection,
} from '../lib/feature-selection';

export interface FeatureSelectorProps {
  features: Feature[];
  loading?: boolean;
  selections: FeatureSelection[];
  onToggle: (feature: Feature) => void;
  onParamsChange: (feature: string, params: Record<string, string>) => void;
}

/** Purpose/columns/warmup/version for one generator, as tooltip sections. */
function tooltipSections(feature: Feature) {
  return [
    { heading: 'Purpose', body: feature.description },
    {
      heading: 'Columns produced',
      body: feature.outputs.length > 0 ? feature.outputs.join(', ') : 'Not documented.',
    },
    { heading: 'Warmup', body: feature.warmup_description || 'None.' },
    { heading: 'Complexity', body: feature.complexity },
    { heading: 'Version', body: `${feature.version} · ${feature.author}` },
  ];
}

/** Feature Details shown for a selected feature: description, warmup, and dependencies. */
function FeatureDetails({ feature }: { feature: Feature }) {
  const dependencies = feature.dependencies ?? [];
  return (
    <Stack spacing={0.75} sx={{ pb: feature.parameters.length > 0 ? 1 : 1.5 }}>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase' }}>
          Description
        </Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {feature.description}
      </Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Warmup: {feature.warmup_description || 'None'}
          </Typography>
          <InfoTooltip
            label="Warmup Rows"
            sections={[
              {
                heading: 'Warmup Rows',
                body: 'Candles a feature needs before its first defined value. Rows still inside warmup are dropped from the dataset by default, since a training matrix must not contain missing values.',
              },
            ]}
          />
        </Stack>
        <Stack direction="row" spacing={0.25} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            Dependencies: {dependencies.length > 0 ? dependencies.join(', ') : 'None'}
          </Typography>
          <InfoTooltip
            label="Dependencies"
            sections={[
              {
                heading: 'Dependencies',
                body: 'Other registered features this one needs alongside it in the same dataset request. None of the built-in features depend on another today — this is a documented extension point for a future derived feature.',
              },
            ]}
          />
        </Stack>
      </Stack>
    </Stack>
  );
}

interface FeatureRowProps {
  feature: Feature;
  selection: FeatureSelection | undefined;
  favorite: boolean;
  onToggle: (feature: Feature) => void;
  onToggleFavorite: (feature: Feature) => void;
  onParamsChange: (feature: string, params: Record<string, string>) => void;
  checkboxRef?: (element: HTMLInputElement | null) => void;
}

function FeatureRow({
  feature,
  selection,
  favorite,
  onToggle,
  onToggleFavorite,
  onParamsChange,
  checkboxRef,
}: FeatureRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const selected = selection !== undefined;
  const configurable = feature.parameters.length > 0;
  const columnCount = feature.outputs.length;

  const handleParameterChange = (name: string, value: string) => {
    if (!selection) {
      return;
    }
    const next = { ...selection.params, [name]: value };
    const found = validateValues(feature.parameters, next);
    setErrors(found);
    // Commit only a fully-valid parameter set. Sending a value we already
    // know is out of range would just spend a round trip to be told so,
    // and would replace a working dataset with an error state mid-edit.
    if (Object.keys(found).length === 0) {
      onParamsChange(feature.name, next);
    }
  };

  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      <Stack direction="row" spacing={0.5} alignItems="flex-start" sx={{ py: 0.25 }}>
        <Checkbox
          size="small"
          checked={selected}
          onChange={() => onToggle(feature)}
          inputRef={checkboxRef}
          slotProps={{ input: { 'aria-label': `Include ${feature.label}` } }}
        />
        <IconButton
          size="small"
          onClick={() => onToggleFavorite(feature)}
          aria-label={
            favorite
              ? `Remove ${feature.label} from favorites`
              : `Add ${feature.label} to favorites`
          }
          aria-pressed={favorite}
          sx={{ mt: 0.25 }}
        >
          {favorite ? (
            <StarIcon fontSize="small" sx={{ color: 'warning.main' }} />
          ) : (
            <StarBorderIcon fontSize="small" />
          )}
        </IconButton>
        <ListItemText
          primary={
            <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
              <Typography variant="body2" sx={{ fontWeight: selected ? 600 : 400 }}>
                {feature.label}
              </Typography>
              <InfoTooltip label={feature.label} sections={tooltipSections(feature)} />
              {selected && configurable ? (
                <Chip size="small" variant="outlined" label={paramSummary(selection)} />
              ) : null}
            </Stack>
          }
          secondary={
            <Stack component="span" spacing={0}>
              <Typography component="span" variant="caption" noWrap display="block">
                {feature.description}
              </Typography>
              <Typography component="span" variant="caption" color="text.secondary" display="block">
                v{feature.version} · {feature.category} · {columnCount}{' '}
                {columnCount === 1 ? 'column' : 'columns'}
              </Typography>
            </Stack>
          }
          sx={{ my: 0 }}
        />
        {selected ? (
          <IconButton
            size="small"
            aria-label={`Show details for ${feature.label}`}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            <TuneIcon fontSize="small" />
          </IconButton>
        ) : null}
      </Stack>
      {selection ? (
        <Collapse in={expanded} unmountOnExit>
          <Box sx={{ pl: 8, pr: 1 }}>
            <FeatureDetails feature={feature} />
            {configurable ? (
              <ParameterForm
                specs={feature.parameters}
                values={selection.params}
                errors={errors}
                onChange={handleParameterChange}
              />
            ) : null}
          </Box>
        </Collapse>
      ) : null}
    </ListItem>
  );
}

function SelectorSkeleton() {
  return (
    <Stack spacing={1} role="status" aria-label="Loading feature catalogue">
      {[0, 1, 2, 3, 4].map((key) => (
        <Skeleton key={key} variant="rounded" height={36} />
      ))}
    </Stack>
  );
}

/** One row of quick-pick chips — shared by "Recently used" and "Favorites" so neither duplicates the other's rendering. */
function QuickPickRow({
  icon,
  label,
  features,
  selections,
  onToggle,
  chipContext,
}: {
  icon: ReactNode;
  label: string;
  features: Feature[];
  selections: FeatureSelection[];
  onToggle: (feature: Feature) => void;
  chipContext: string;
}) {
  if (features.length === 0) {
    return null;
  }
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
      {icon}
      <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
        {label}
      </Typography>
      {features.map((feature) => (
        <Chip
          key={feature.name}
          size="small"
          label={feature.label}
          color={isSelected(selections, feature.name) ? 'primary' : 'default'}
          variant={isSelected(selections, feature.name) ? 'filled' : 'outlined'}
          onClick={() => onToggle(feature)}
          aria-label={`Toggle ${feature.label} (${chipContext})`}
        />
      ))}
    </Stack>
  );
}

const ALL_CATEGORIES = '__all__';

/**
 * Which features to include in the dataset: searchable, filterable by
 * category, keyboard-navigable, with quick-pick rows for recently-used and
 * favorited features, per-category expand/collapse, and Select All/Clear
 * All for working with a large feature set quickly.
 *
 * Has **no per-feature code of its own**: the list, each generator's
 * parameters, their bounds, and their descriptions all come from the
 * catalogue response, and the parameter inputs are rendered by
 * `ParameterForm` — the same component the Technical Indicators page uses,
 * reused unchanged because the backend publishes feature parameters with
 * the same `ParameterSpec` type it publishes indicator parameters with.
 *
 * The consequence is the frontend half of the extensibility guarantee: a
 * generator registered on the backend appears here, correctly constrained
 * and documented, with no change to this file.
 */
export function FeatureSelector({
  features,
  loading = false,
  selections,
  onToggle,
  onParamsChange,
}: FeatureSelectorProps) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [collapsedCategories, setCollapsedCategories] = useState<ReadonlySet<string>>(new Set());
  const recent = useRecentFeaturesStore((state) => state.recent);
  const favorites = useFavoriteFeaturesStore((state) => state.favorites);
  const checkboxRefs = useRef<Map<string, HTMLInputElement>>(new Map());

  const categories = useMemo(
    () => Array.from(new Set(features.map((feature) => feature.category))).sort(),
    [features],
  );

  const filtered = useMemo(
    () =>
      features.filter(
        (feature) =>
          matchesCatalogSearch(feature, search) &&
          (category === ALL_CATEGORIES || feature.category === category),
      ),
    [features, search, category],
  );

  const groups = useMemo(() => groupFeaturesByCategory(filtered), [filtered]);

  const recentFeatures = useMemo(
    () =>
      recent
        .map((name) => features.find((feature) => feature.name === name))
        .filter((feature): feature is Feature => feature !== undefined),
    [recent, features],
  );

  const favoriteFeatures = useMemo(
    () => features.filter((feature) => favorites.includes(feature.name)),
    [features, favorites],
  );

  // Only rows in an *expanded* group are reachable by keyboard, matching
  // what's actually rendered — a collapsed category's rows are as
  // unreachable to the keyboard as they are invisible to the eye.
  const visibleNames = useMemo(
    () =>
      groups
        .filter((group) => !collapsedCategories.has(group.key))
        .flatMap((group) => group.features.map((feature) => feature.name)),
    [groups, collapsedCategories],
  );

  const handleToggle = (feature: Feature) => {
    // Recency is recorded on *every* toggle (add or remove), not only on
    // add: deliberately removing a feature still counts as recent interest
    // in it for this session, and tracking only additions would make the
    // quick-pick list forget a feature the moment it was briefly toggled
    // off to compare a dataset without it.
    useRecentFeaturesStore.getState().recordUsed(feature.name);
    onToggle(feature);
  };

  const handleToggleFavorite = (feature: Feature) => {
    useFavoriteFeaturesStore.getState().toggle(feature.name);
  };

  const handleSelectAll = () => {
    for (const feature of filtered) {
      if (!isSelected(selections, feature.name)) {
        handleToggle(feature);
      }
    }
  };

  const handleClearAll = () => {
    for (const selection of selections) {
      const feature = features.find((entry) => entry.name === selection.feature);
      if (feature) {
        handleToggle(feature);
      }
    }
  };

  const toggleCategoryCollapsed = (key: string) => {
    setCollapsedCategories((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const expandAll = () => setCollapsedCategories(new Set());
  const collapseAll = () => setCollapsedCategories(new Set(groups.map((group) => group.key)));

  // Roving keyboard navigation: ArrowUp/ArrowDown moves focus between the
  // checkboxes currently visible under the active search/category filter
  // and expand/collapse state, in the same order they're rendered — a
  // keyboard-only researcher can therefore always reach every visible
  // feature without touching a mouse.
  const handleKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
      return;
    }
    const current = (event.target as HTMLElement).getAttribute('data-feature-name');
    const index = current ? visibleNames.indexOf(current) : -1;
    const delta = event.key === 'ArrowDown' ? 1 : -1;
    const nextIndex =
      index === -1 ? 0 : (index + delta + visibleNames.length) % visibleNames.length;
    const nextName = visibleNames[nextIndex];
    if (nextName) {
      checkboxRefs.current.get(nextName)?.focus();
      event.preventDefault();
    }
  };

  if (loading) {
    return <SelectorSkeleton />;
  }

  if (features.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No feature generators are registered.
      </Typography>
    );
  }

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1}>
        <TextField
          size="small"
          placeholder="Search features…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ flex: 1 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
            htmlInput: { 'aria-label': 'Search features' },
          }}
        />
        <TextField
          select
          label="Category"
          size="small"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value={ALL_CATEGORIES}>All categories</MenuItem>
          {categories.map((entry) => (
            <MenuItem key={entry} value={entry}>
              {entry}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button size="small" onClick={handleSelectAll} disabled={filtered.length === 0}>
          Select All
        </Button>
        <Button size="small" onClick={handleClearAll} disabled={selections.length === 0}>
          Clear All
        </Button>
        <Button size="small" onClick={expandAll} disabled={collapsedCategories.size === 0}>
          Expand All
        </Button>
        <Button
          size="small"
          onClick={collapseAll}
          disabled={collapsedCategories.size === groups.length}
        >
          Collapse All
        </Button>
      </Stack>

      <QuickPickRow
        icon={<HistoryIcon fontSize="small" sx={{ color: 'text.secondary' }} aria-hidden />}
        label="Recently used:"
        features={recentFeatures}
        selections={selections}
        onToggle={handleToggle}
        chipContext="recently used"
      />

      <QuickPickRow
        icon={<StarIcon fontSize="small" sx={{ color: 'warning.main' }} aria-hidden />}
        label="Favorites:"
        features={favoriteFeatures}
        selections={selections}
        onToggle={handleToggle}
        chipContext="favorite"
      />

      {recentFeatures.length > 0 || favoriteFeatures.length > 0 ? <Divider /> : null}

      {filtered.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
          No features match “{search}”.
        </Typography>
      ) : (
        <List
          dense
          disablePadding
          aria-label="Available features"
          subheader={<li />}
          onKeyDown={handleKeyDown}
        >
          {groups.map((group) => {
            const collapsed = collapsedCategories.has(group.key);
            return (
              <li key={group.key}>
                <ul style={{ padding: 0 }}>
                  <ListSubheader
                    disableSticky
                    sx={{
                      lineHeight: 2.25,
                      bgcolor: 'transparent',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                    }}
                  >
                    <IconButton
                      size="small"
                      onClick={() => toggleCategoryCollapsed(group.key)}
                      aria-label={collapsed ? `Expand ${group.label}` : `Collapse ${group.label}`}
                      aria-expanded={!collapsed}
                    >
                      {collapsed ? (
                        <ExpandMoreIcon fontSize="small" />
                      ) : (
                        <ExpandLessIcon fontSize="small" />
                      )}
                    </IconButton>
                    {group.label}
                    <Typography variant="caption" color="text.secondary">
                      ({group.features.length})
                    </Typography>
                  </ListSubheader>
                  <Collapse in={!collapsed} unmountOnExit>
                    {group.features.map((feature) => (
                      <FeatureRow
                        key={feature.name}
                        feature={feature}
                        selection={selections.find((s) => s.feature === feature.name)}
                        favorite={favorites.includes(feature.name)}
                        onToggle={handleToggle}
                        onToggleFavorite={handleToggleFavorite}
                        onParamsChange={onParamsChange}
                        checkboxRef={(element) => {
                          if (element) {
                            checkboxRefs.current.set(feature.name, element);
                            element.setAttribute('data-feature-name', feature.name);
                          } else {
                            checkboxRefs.current.delete(feature.name);
                          }
                        }}
                      />
                    ))}
                  </Collapse>
                </ul>
              </li>
            );
          })}
        </List>
      )}
    </Stack>
  );
}

export { isSelected };
