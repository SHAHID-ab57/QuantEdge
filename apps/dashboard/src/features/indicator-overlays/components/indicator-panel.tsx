'use client';

import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SearchOffIcon from '@mui/icons-material/SearchOff';
import SearchIcon from '@mui/icons-material/Search';
import TuneIcon from '@mui/icons-material/Tune';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';
import { memo, useMemo, useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { resolveOverlayColor } from '@/components/chart/overlay-colors';
import {
  getIndicatorKnowledge,
  toTooltipSections,
} from '@/features/indicators/lib/indicator-knowledge';
import { ParameterForm } from '@/features/indicators/components/parameter-form';
import { validateValues } from '@/features/indicators/lib/parameter-values';
import type { Indicator } from '@/types/api/indicators';
import { groupIndicatorsByCategory } from '../lib/categorize';
import { matchesIndicatorSearch } from '../lib/search-indicators';
import { useOverlayStore, type OverlayConfig } from '../store/use-overlay-store';
import { OverlayColorSwatch } from './overlay-color-swatch';

export interface IndicatorPanelProps {
  indicators: Indicator[];
  loading?: boolean;
}

interface OverlayRowProps {
  overlay: OverlayConfig;
  /** The overlay's own parameter specs, looked up once by the parent from the catalogue — never re-fetched per row. */
  specs: Indicator['parameters'];
}

function OverlayRow({ overlay, specs }: OverlayRowProps) {
  const theme = useTheme();
  const removeOverlay = useOverlayStore((state) => state.removeOverlay);
  const toggleOverlay = useOverlayStore((state) => state.toggleOverlay);
  const updateOverlayParams = useOverlayStore((state) => state.updateOverlayParams);
  const setOverlayColor = useOverlayStore((state) => state.setOverlayColor);

  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(overlay.params);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const color = resolveOverlayColor(theme, overlay.colorIndex, overlay.colorOverride);
  const paramSummary =
    Object.entries(overlay.params)
      .map(([key, value]) => `${key}=${value}`)
      .join(', ') || 'default parameters';

  const handleParameterChange = (name: string, value: string) => {
    const nextDraft = { ...draft, [name]: value };
    setDraft(nextDraft);
    const found = validateValues(specs, nextDraft);
    setErrors(found);
    // Commit to the store — and therefore to the chart — only once the
    // whole draft is valid, mirroring the standalone Indicators page's
    // own "don't fire a request from a value we already know is bad"
    // discipline. The chart keeps showing the last valid configuration
    // while a researcher is mid-edit rather than flashing an error state
    // on every keystroke.
    if (Object.keys(found).length === 0) {
      updateOverlayParams(overlay.id, nextDraft);
    }
  };

  return (
    <ListItem
      disablePadding
      sx={{ display: 'block', borderBottom: `1px solid ${theme.palette.divider}` }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 1, py: 0.75 }}>
        <OverlayColorSwatch
          color={color}
          label={overlay.label}
          isOverride={Boolean(overlay.colorOverride)}
          onSelect={(next) => setOverlayColor(overlay.id, next)}
          onReset={() => setOverlayColor(overlay.id, null)}
        />
        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
            {overlay.label}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {paramSummary}
          </Typography>
        </Stack>
        <Switch
          size="small"
          checked={overlay.enabled}
          onChange={() => toggleOverlay(overlay.id)}
          slotProps={{
            input: {
              'aria-label': `${overlay.enabled ? 'Disable' : 'Enable'} ${overlay.label}`,
            },
          }}
        />
        <IconButton
          size="small"
          aria-label={`Configure ${overlay.label}`}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <TuneIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          aria-label={`Remove ${overlay.label}`}
          onClick={() => removeOverlay(overlay.id)}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Stack>
      {expanded ? (
        <Box sx={{ px: 1, pb: 1.5 }}>
          <ParameterForm
            specs={specs}
            values={draft}
            errors={errors}
            onChange={handleParameterChange}
          />
        </Box>
      ) : null}
    </ListItem>
  );
}

interface AvailableIndicatorsListProps {
  loading: boolean;
  filtered: Indicator[];
  search: string;
  addedNames: Set<string>;
  onAdd: (indicator: Indicator) => void;
  onClearSearch: () => void;
}

function AvailableIndicatorsLoading() {
  return (
    <Stack spacing={0.75} sx={{ p: 1.5 }} aria-label="Loading indicators" role="status">
      {[0, 1, 2, 3].map((key) => (
        <Skeleton key={key} variant="rounded" height={40} />
      ))}
    </Stack>
  );
}

function AvailableIndicatorsEmpty({
  search,
  onClearSearch,
}: {
  search: string;
  onClearSearch: () => void;
}) {
  return (
    <Stack spacing={1} alignItems="center" sx={{ p: 2.5, textAlign: 'center' }}>
      <SearchOffIcon color="disabled" />
      <Typography variant="body2" color="text.secondary">
        No indicators match “{search}”.
      </Typography>
      <Button size="small" onClick={onClearSearch}>
        Clear search
      </Button>
    </Stack>
  );
}

/**
 * The three mutually-exclusive states of the catalogue list — loading,
 * no search matches, or the grouped list itself — as flat early returns
 * rather than a nested ternary. Indicators are grouped by category
 * (`groupIndicatorsByCategory`) so the panel reads as organized sections
 * (Trend, Momentum, Volatility, Volume, Oscillators, Statistical, Other)
 * rather than one flat alphabetical list — this is what lets the panel
 * stay usable as the catalogue grows toward dozens of indicators.
 */
function AvailableIndicatorsList({
  loading,
  filtered,
  search,
  addedNames,
  onAdd,
  onClearSearch,
}: AvailableIndicatorsListProps) {
  if (loading) {
    return <AvailableIndicatorsLoading />;
  }

  if (filtered.length === 0) {
    return <AvailableIndicatorsEmpty search={search} onClearSearch={onClearSearch} />;
  }

  const groups = groupIndicatorsByCategory(filtered);

  return (
    <List dense disablePadding aria-label="Available indicators" subheader={<li />}>
      {groups.map((group) => (
        <li key={group.key}>
          <ul style={{ padding: 0 }}>
            <ListSubheader disableSticky sx={{ lineHeight: 2.5 }}>
              {group.label}
            </ListSubheader>
            {group.indicators.map((indicator) => {
              const knowledge = getIndicatorKnowledge(indicator);
              return (
                <ListItem
                  key={indicator.name}
                  disablePadding
                  secondaryAction={
                    <IconButton
                      size="small"
                      edge="end"
                      aria-label={`Add ${indicator.label}`}
                      onClick={() => onAdd(indicator)}
                    >
                      <AddIcon fontSize="small" />
                    </IconButton>
                  }
                >
                  <ListItemButton onClick={() => onAdd(indicator)} sx={{ pr: 6 }}>
                    <ListItemText
                      primary={
                        <Stack direction="row" spacing={0.5} alignItems="center">
                          <Typography variant="body2">{indicator.label}</Typography>
                          <InfoTooltip
                            label={indicator.label}
                            sections={toTooltipSections(knowledge)}
                            maxWidth={340}
                          />
                          {addedNames.has(indicator.name) ? (
                            <Chip label="Added" size="small" color="primary" />
                          ) : null}
                        </Stack>
                      }
                      secondary={indicator.description}
                      slotProps={{ secondary: { noWrap: true } }}
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </ul>
        </li>
      ))}
    </List>
  );
}

/**
 * Indicator search, add, and the list of currently-configured overlays —
 * the Indicator Panel half of the Indicator Management & Chart Overlay
 * System. Reuses `useIndicatorCatalog` (no duplicate catalogue fetch),
 * `ParameterForm` (no duplicate parameter-form implementation), and
 * `getIndicatorKnowledge`/`toTooltipSections` (no duplicate research
 * content) from the standalone `/indicators` research page's feature
 * module — this panel has no per-indicator code of its own, the same
 * guarantee that page makes.
 */
function IndicatorPanelInner({ indicators, loading = false }: IndicatorPanelProps) {
  const [search, setSearch] = useState('');
  const overlays = useOverlayStore((state) => state.overlays);
  const addOverlay = useOverlayStore((state) => state.addOverlay);

  const specsByName = useMemo(
    () => new Map(indicators.map((indicator) => [indicator.name, indicator.parameters])),
    [indicators],
  );

  const filtered = useMemo(
    () => indicators.filter((indicator) => matchesIndicatorSearch(indicator, search)),
    [indicators, search],
  );

  const addedNames = new Set(overlays.map((overlay) => overlay.indicator));

  return (
    <Stack spacing={1.5}>
      <TextField
        size="small"
        placeholder="Search by name, category, alias, or description…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
          htmlInput: { 'aria-label': 'Search indicators' },
        }}
      />

      {/* `defaultExpanded` is a genuine uncontrolled default (read once on
          mount only) — it must not be derived from `overlays.length`,
          which changes as overlays are added/removed and would otherwise
          make MUI warn about an uncontrolled Accordion's default changing
          after initialization. */}
      <Accordion variant="outlined" disableGutters defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2">Available Indicators</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          <AvailableIndicatorsList
            loading={loading}
            filtered={filtered}
            search={search}
            addedNames={addedNames}
            onAdd={addOverlay}
            onClearSearch={() => setSearch('')}
          />
        </AccordionDetails>
      </Accordion>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Chart Overlays {overlays.length > 0 ? `(${overlays.length})` : ''}
        </Typography>
        {overlays.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Add an indicator above to overlay it on the chart.
          </Typography>
        ) : (
          <List dense disablePadding aria-label="Chart overlays">
            {overlays.map((overlay) => (
              <OverlayRow
                key={overlay.id}
                overlay={overlay}
                specs={specsByName.get(overlay.indicator) ?? []}
              />
            ))}
          </List>
        )}
      </Box>
    </Stack>
  );
}

export const IndicatorPanel = memo(IndicatorPanelInner);
