import type { Theme } from '@mui/material/styles';

/**
 * A fixed rotation of theme palette colors for assigning a distinct color
 * to each of several simultaneously-rendered series — an indicator's own
 * multi-series output (`IndicatorChart`) or several independent overlay
 * indicators on the candlestick chart (`CandlestickChart`'s `overlays`
 * prop). Promoted here once a second consumer needed the identical
 * "cycle through a handful of theme colors by index" logic.
 */
export const OVERLAY_COLOR_KEYS = ['primary', 'secondary', 'warning', 'success'] as const;

export function overlayColor(theme: Theme, index: number): string {
  const key = OVERLAY_COLOR_KEYS[index % OVERLAY_COLOR_KEYS.length]!;
  return theme.palette[key].main;
}

/**
 * The wider palette a researcher can *manually* pick from when the
 * auto-assigned rotation (`OVERLAY_COLOR_KEYS`) isn't distinct enough for
 * their eyes, or when they want two related overlays (e.g. a fast/slow EMA
 * pair) to share a color family. A superset of `OVERLAY_COLOR_KEYS` so the
 * automatic assignment is always also a valid manual choice.
 */
export const OVERLAY_COLOR_PALETTE_KEYS = [
  'primary',
  'secondary',
  'warning',
  'success',
  'error',
  'info',
] as const;

export type OverlayColorPaletteKey = (typeof OVERLAY_COLOR_PALETTE_KEYS)[number];

export interface OverlayColorSwatch {
  key: OverlayColorPaletteKey;
  color: string;
}

export function overlayColorPalette(theme: Theme): OverlayColorSwatch[] {
  return OVERLAY_COLOR_PALETTE_KEYS.map((key) => ({ key, color: theme.palette[key].main }));
}

/**
 * The color actually rendered for one overlay: an explicit manual override
 * when the researcher has set one, otherwise the automatic rotation by
 * `colorIndex` — the "future customization" layer on top of auto-assigned
 * colors, without changing how auto-assignment itself works.
 */
export function resolveOverlayColor(
  theme: Theme,
  colorIndex: number,
  override?: string | null,
): string {
  return override ?? overlayColor(theme, colorIndex);
}
