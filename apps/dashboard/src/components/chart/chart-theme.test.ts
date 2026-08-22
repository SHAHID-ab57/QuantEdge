import { describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import {
  buildCandlestickSeriesOptions,
  buildChartOptions,
  buildVolumeSeriesOptions,
  VOLUME_SCALE_MARGINS,
} from './chart-theme';

describe('buildChartOptions', () => {
  it('maps the MUI palette onto lightweight-charts layout/grid options', () => {
    const options = buildChartOptions(theme);
    expect(options.autoSize).toBe(true);
    expect(options.layout?.textColor).toBe(theme.palette.text.secondary);
    expect(options.grid?.vertLines?.color).toBe(theme.palette.divider);
    expect(options.timeScale?.timeVisible).toBe(true);
  });
});

describe('buildCandlestickSeriesOptions', () => {
  it('uses the theme success color for up candles and error color for down candles', () => {
    const options = buildCandlestickSeriesOptions(theme);
    expect(options.upColor).toBe(theme.palette.success.main);
    expect(options.downColor).toBe(theme.palette.error.main);
    expect(options.wickUpColor).toBe(theme.palette.success.main);
    expect(options.wickDownColor).toBe(theme.palette.error.main);
  });
});

describe('buildVolumeSeriesOptions', () => {
  it('places the volume series on its own overlay price scale', () => {
    const options = buildVolumeSeriesOptions();
    expect(options.priceScaleId).toBe('');
    expect(options.priceFormat).toEqual({ type: 'volume' });
  });
});

describe('VOLUME_SCALE_MARGINS', () => {
  it('reserves the bottom of the pane for the volume histogram', () => {
    expect(VOLUME_SCALE_MARGINS.bottom).toBe(0);
    expect(VOLUME_SCALE_MARGINS.top).toBeGreaterThan(0.5);
  });
});
