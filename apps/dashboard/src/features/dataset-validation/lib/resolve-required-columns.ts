import {
  defaultParamsFor,
  type FeatureSelection,
} from '@/features/feature-engineering/lib/feature-selection';
import type { Feature } from '@/types/api/features';

/**
 * Turns the feature catalogue (Feature Registry metadata, already fetched
 * for the Feature Selector) into a searchable universe of candidate
 * "required column" names — the Required Columns selector's option list.
 *
 * No backend change and no new data source: every column name is derived
 * from a feature's own declared `outputs` templates (e.g. `"sma_{period}"`)
 * resolved against that feature's parameters — the *currently selected*
 * parameters when the feature is selected, or its published defaults
 * otherwise, via the same `defaultParamsFor` the Feature Selector already
 * uses to seed a freshly-ticked feature. This mirrors, on the frontend,
 * exactly how the backend's dataset builder names a column
 * (`app/features/base.py`'s `FeatureColumn.name`), without duplicating
 * that logic server-side or guessing at it.
 */

export interface RequiredColumnOption {
  /** The resolved column name, e.g. "sma_20" — what gets sent as `required_columns`. */
  name: string;
  feature: string;
  featureLabel: string;
  /** One of the five UI buckets — see `columnCategoryFor`. */
  category: string;
}

/**
 * Maps a feature's backend `category` (a free-form string — "raw",
 * "trend", "momentum", ...) onto one of five fixed UI buckets. Any
 * category this map doesn't recognize falls into "Future Features" —
 * deliberately, so a brand-new backend category still renders in a
 * readable group rather than being dropped, the same graceful-fallback
 * guarantee `groupByCategory` already gives the Feature Selector itself.
 */
const CATEGORY_BUCKETS: Record<string, string> = {
  raw: 'Raw Market Data',
  trend: 'Technical Indicators',
  momentum: 'Technical Indicators',
  volatility: 'Technical Indicators',
  volume: 'Technical Indicators',
  price_action: 'Candle Features',
  statistical: 'Statistical Features',
};

export const REQUIRED_COLUMN_CATEGORY_ORDER: readonly string[] = [
  'Raw Market Data',
  'Technical Indicators',
  'Candle Features',
  'Statistical Features',
  'Future Features',
];

export function columnCategoryFor(featureCategory: string): string {
  return CATEGORY_BUCKETS[featureCategory] ?? 'Future Features';
}

/** Replace every `{param}` placeholder in an output template with its resolved value. */
function resolveTemplate(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => params[key] ?? match);
}

/**
 * Every candidate required-column name across the whole catalogue, deduped
 * by resolved name. A feature currently selected resolves its templates
 * against its *actual* chosen parameters (so picking `sma` with
 * `period=50` offers `sma_50`, not the default `sma_20`); an unselected
 * feature resolves against its published defaults, so its likely columns
 * are still discoverable before it's ever ticked.
 */
export function resolveRequiredColumnOptions(
  features: readonly Feature[],
  selections: readonly FeatureSelection[],
): RequiredColumnOption[] {
  const paramsByFeature = new Map(
    selections.map((selection) => [selection.feature, selection.params]),
  );
  const seen = new Set<string>();
  const options: RequiredColumnOption[] = [];

  for (const feature of features) {
    const params = paramsByFeature.get(feature.name) ?? defaultParamsFor(feature);
    for (const template of feature.outputs) {
      const name = resolveTemplate(template, params);
      if (seen.has(name)) {
        continue;
      }
      seen.add(name);
      options.push({
        name,
        feature: feature.name,
        featureLabel: feature.label,
        category: columnCategoryFor(feature.category),
      });
    }
  }
  return options;
}

/** A curated shortcut for a common required-columns configuration. */
export type ColumnPresetKey =
  'raw_market_data' | 'ohlcv_only' | 'trend_indicators' | 'ai_basic_features' | 'full_dataset';

export interface ColumnPreset {
  key: ColumnPresetKey;
  label: string;
  description: string;
}

export const COLUMN_PRESETS: readonly ColumnPreset[] = [
  {
    key: 'raw_market_data',
    label: 'Raw Market Data',
    description: 'Every raw-category feature — today, that is OHLCV.',
  },
  {
    key: 'ohlcv_only',
    label: 'OHLCV Only',
    description: 'Just open, high, low, close, and volume.',
  },
  {
    key: 'trend_indicators',
    label: 'Trend Indicators',
    description: 'Every trend-category feature at its default parameters (e.g. SMA, EMA, WMA).',
  },
  {
    key: 'ai_basic_features',
    label: 'AI Basic Features',
    description: 'A minimal starter set for a first model: OHLCV, candle shape, and SMA.',
  },
  {
    key: 'full_dataset',
    label: 'Full Dataset',
    description: 'Every registered feature in the catalogue.',
  },
];

/** Names chosen for the "AI Basic Features" preset — a small, opinionated starter bundle. */
const AI_BASIC_FEATURE_NAMES: readonly string[] = ['ohlcv', 'candle_shape', 'sma'];

/**
 * Resolve one preset key into the concrete features it selects, straight
 * from the live catalogue — never a hardcoded feature list independent of
 * what the backend actually registers. A preset whose target feature
 * isn't registered (e.g. "trend_indicators" before any trend feature
 * exists) simply resolves to an empty set rather than erroring.
 */
export function resolvePresetFeatures(
  features: readonly Feature[],
  key: ColumnPresetKey,
): Feature[] {
  switch (key) {
    case 'raw_market_data':
      return features.filter((feature) => feature.category === 'raw');
    case 'ohlcv_only':
      return features.filter((feature) => feature.name === 'ohlcv');
    case 'trend_indicators':
      return features.filter((feature) => feature.category === 'trend');
    case 'ai_basic_features':
      return features.filter((feature) => AI_BASIC_FEATURE_NAMES.includes(feature.name));
    case 'full_dataset':
      return [...features];
    default:
      return [];
  }
}
