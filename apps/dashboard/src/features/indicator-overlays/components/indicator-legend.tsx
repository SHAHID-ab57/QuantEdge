'use client';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import CloseIcon from '@mui/icons-material/Close';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';
import { memo, useState, type DragEvent } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { resolveOverlayColor } from '@/components/chart/overlay-colors';
import type { OverlayChartSeries } from '../lib/overlay-series';
import { useOverlayStore, type OverlayConfig } from '../store/use-overlay-store';
import { OverlayColorSwatch } from './overlay-color-swatch';
import { OverlayExportMenu } from './overlay-export-menu';

export interface IndicatorLegendProps {
  overlays: readonly OverlayConfig[];
  /** Per-overlay computed result (success/error, calculation metadata) — omit while nothing has loaded yet. */
  overlaySeries?: readonly OverlayChartSeries[];
  /** True while a batch calculation is in flight, for a per-row loading affordance. */
  isLoading?: boolean;
  /** Needed only to name the exported file/payload; omit to hide the export action. */
  symbol?: string;
  timeframe?: string;
}

function paramSummary(overlay: OverlayConfig): string {
  const pairs = Object.entries(overlay.params).map(([key, value]) => `${key}=${value}`);
  return pairs.length > 0 ? pairs.join(', ') : 'default parameters';
}

function formatMs(value: number | null): string {
  return value === null ? 'n/a' : `${value.toFixed(2)} ms`;
}

function detailsSections(series: OverlayChartSeries | undefined) {
  const meta = series?.meta;
  return [
    { heading: 'Calculation Time', body: formatMs(meta?.executionTimeMs ?? null) },
    { heading: 'Cache Status', body: meta?.cacheStatus ?? 'n/a' },
    {
      heading: 'Dataset Size',
      body: meta ? `${meta.candlesAnalyzed} candles` : 'n/a',
    },
    {
      heading: 'Warmup Period',
      body:
        meta?.warmupCandles !== null && meta?.warmupCandles !== undefined
          ? `${meta.warmupCandles} candles`
          : 'n/a',
    },
    { heading: 'Engine Version', body: meta?.engineVersion ?? 'n/a' },
    { heading: 'Source Price', body: meta?.sourceParam ?? 'n/a' },
  ];
}

interface LegendEntryProps {
  overlay: OverlayConfig;
  series?: OverlayChartSeries;
  index: number;
  total: number;
  loading: boolean;
  onDragStart: (id: string) => void;
  onDropOn: (id: string) => void;
}

function LegendEntry({
  overlay,
  series,
  index,
  total,
  loading,
  onDragStart,
  onDropOn,
}: LegendEntryProps) {
  const theme = useTheme();
  const toggleOverlay = useOverlayStore((state) => state.toggleOverlay);
  const removeOverlay = useOverlayStore((state) => state.removeOverlay);
  const setOverlayColor = useOverlayStore((state) => state.setOverlayColor);
  const moveOverlayToIndex = useOverlayStore((state) => state.moveOverlayToIndex);
  const color = resolveOverlayColor(theme, overlay.colorIndex, overlay.colorOverride);
  const [dragOver, setDragOver] = useState(false);

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      draggable
      onDragStart={(event: DragEvent<HTMLDivElement>) => {
        event.dataTransfer.setData('text/plain', overlay.id);
        onDragStart(overlay.id);
      }}
      onDragOver={(event: DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event: DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setDragOver(false);
        onDropOn(overlay.id);
      }}
      sx={{
        opacity: overlay.enabled ? 1 : 0.5,
        p: 0.5,
        borderRadius: 1,
        bgcolor: dragOver ? 'action.hover' : 'transparent',
        border: '1px dashed transparent',
        borderColor: dragOver ? 'divider' : 'transparent',
      }}
    >
      <DragIndicatorIcon
        fontSize="small"
        sx={{ color: 'text.disabled', cursor: 'grab' }}
        aria-hidden
      />
      <Stack direction="column" spacing={0}>
        <IconButton
          size="small"
          aria-label={`Move ${overlay.label} up`}
          disabled={index === 0}
          onClick={() => moveOverlayToIndex(overlay.id, index - 1)}
          sx={{ p: 0 }}
        >
          <ArrowUpwardIcon sx={{ fontSize: 12 }} />
        </IconButton>
        <IconButton
          size="small"
          aria-label={`Move ${overlay.label} down`}
          disabled={index === total - 1}
          onClick={() => moveOverlayToIndex(overlay.id, index + 1)}
          sx={{ p: 0 }}
        >
          <ArrowDownwardIcon sx={{ fontSize: 12 }} />
        </IconButton>
      </Stack>
      <OverlayColorSwatch
        color={color}
        label={overlay.label}
        isOverride={Boolean(overlay.colorOverride)}
        onSelect={(next) => setOverlayColor(overlay.id, next)}
        onReset={() => setOverlayColor(overlay.id, null)}
      />
      <Typography variant="caption" sx={{ fontWeight: 600 }}>
        {overlay.label}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {paramSummary(overlay)}
      </Typography>
      {loading ? <CircularProgress size={10} thickness={6} aria-label="Recalculating" /> : null}
      {!loading && series && !series.ok ? (
        <Tooltip title={series.error ?? 'This overlay failed to calculate.'}>
          <Typography variant="caption" color="error.main" sx={{ fontWeight: 600 }}>
            Error
          </Typography>
        </Tooltip>
      ) : null}
      <InfoTooltip
        label={`${overlay.label} calculation details`}
        sections={detailsSections(series)}
      />
      <Tooltip title={overlay.enabled ? 'Hide on chart' : 'Show on chart'}>
        <IconButton
          size="small"
          aria-label={`${overlay.enabled ? 'Hide' : 'Show'} ${overlay.label}`}
          onClick={() => toggleOverlay(overlay.id)}
        >
          {overlay.enabled ? (
            <VisibilityIcon sx={{ fontSize: 14 }} />
          ) : (
            <VisibilityOffIcon sx={{ fontSize: 14 }} />
          )}
        </IconButton>
      </Tooltip>
      <Tooltip title="Remove overlay">
        <IconButton
          size="small"
          aria-label={`Remove ${overlay.label}`}
          onClick={() => removeOverlay(overlay.id)}
        >
          <CloseIcon sx={{ fontSize: 14 }} />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

/**
 * A compact, chart-adjacent readout of every configured overlay — Name,
 * Parameters, Visibility, and Remove, per the Indicator Management & Chart
 * Overlay System's contract — plus color customization, drag-and-drop (and
 * keyboard-accessible up/down) reordering, calculation-detail tooltips, and
 * a set-level export menu. Distinct from `IndicatorPanel`'s fuller
 * management UI (search, add, configure); both read from and write to the
 * same `useOverlayStore`, so an action taken here or in the panel is the
 * same action wherever it's triggered from.
 *
 * Reordering here *is* the chart's render order: `moveOverlayToIndex`
 * writes directly to the store's `overlays` array order, which
 * `useChartOverlays`/`CandlestickChart` read back unmodified — see
 * `ARCHITECTURE.md` § "Indicator Management & Chart Overlay System".
 */
function IndicatorLegendInner({
  overlays,
  overlaySeries = [],
  isLoading = false,
  symbol,
  timeframe,
}: IndicatorLegendProps) {
  const moveOverlayToIndex = useOverlayStore((state) => state.moveOverlayToIndex);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const seriesById = new Map(overlaySeries.map((series) => [series.id, series]));

  if (overlays.length === 0) {
    return (
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ color: 'text.secondary', py: 1 }}
      >
        <LayersOutlinedIcon fontSize="small" />
        <Typography variant="caption">
          No indicator overlays added. Add one from the Indicators panel to see it here.
        </Typography>
      </Stack>
    );
  }

  const handleDropOn = (targetId: string) => {
    if (draggingId && draggingId !== targetId) {
      const targetIndex = overlays.findIndex((overlay) => overlay.id === targetId);
      if (targetIndex !== -1) {
        moveOverlayToIndex(draggingId, targetIndex);
      }
    }
    setDraggingId(null);
  };

  return (
    <Stack spacing={0.75}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        useFlexGap
      >
        <Typography variant="caption" color="text.secondary">
          Drag, or use the arrows, to reorder — render order follows this list.
        </Typography>
        {symbol && timeframe ? (
          <OverlayExportMenu symbol={symbol} timeframe={timeframe} overlays={[...overlaySeries]} />
        ) : null}
      </Stack>
      <Stack spacing={0.5} aria-label="Indicator overlays">
        {overlays.map((overlay, index) => (
          <LegendEntry
            key={overlay.id}
            overlay={overlay}
            series={seriesById.get(overlay.id)}
            index={index}
            total={overlays.length}
            loading={isLoading}
            onDragStart={setDraggingId}
            onDropOn={handleDropOn}
          />
        ))}
      </Stack>
    </Stack>
  );
}

export const IndicatorLegend = memo(IndicatorLegendInner);
