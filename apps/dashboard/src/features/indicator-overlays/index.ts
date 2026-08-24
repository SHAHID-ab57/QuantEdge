export { useOverlayStore, type OverlayConfig } from './store/use-overlay-store';
export { useChartOverlays, type UseChartOverlaysInput } from './hooks/use-chart-overlays';
export { useOverlayCalculations } from './hooks/use-overlay-calculations';
export {
  toOverlaySeries,
  createOverlaySeriesCache,
  type OverlayChartSeries,
  type OverlayResultMeta,
} from './lib/overlay-series';
export { groupIndicatorsByCategory, type IndicatorCategoryGroup } from './lib/categorize';
export { matchesIndicatorSearch } from './lib/search-indicators';
export { IndicatorPanel, type IndicatorPanelProps } from './components/indicator-panel';
export { IndicatorLegend, type IndicatorLegendProps } from './components/indicator-legend';
export { OverlayColorSwatch } from './components/overlay-color-swatch';
export { OverlayExportMenu } from './components/overlay-export-menu';
