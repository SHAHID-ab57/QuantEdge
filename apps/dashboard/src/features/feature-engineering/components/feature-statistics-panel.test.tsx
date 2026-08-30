import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureStatistics } from '@/types/api/features';
import { FeatureStatisticsPanel } from './feature-statistics-panel';

afterEach(() => cleanup());

describe('FeatureStatisticsPanel', () => {
  it('renders one row per column with its stats', () => {
    const statistics: FeatureStatistics = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      columns: [
        {
          column: 'close',
          count: 3,
          null_count: 0,
          mean: 22.333333,
          std: 8.73689,
          minimum: 11,
          maximum: 32,
        },
      ],
      row_count: 3,
    };
    render(
      <ThemeProvider theme={theme}>
        <FeatureStatisticsPanel statistics={statistics} />
      </ThemeProvider>,
    );
    expect(screen.getByText('close')).toBeInTheDocument();
    expect(screen.getByText('11')).toBeInTheDocument();
    expect(screen.getByText('32')).toBeInTheDocument();
    expect(screen.getByText(/Computed over all 3 rows/)).toBeInTheDocument();
  });

  it('shows a placeholder for a non-numeric column', () => {
    const statistics: FeatureStatistics = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      columns: [
        {
          column: 'candle_direction',
          count: 3,
          null_count: 0,
          mean: null,
          std: null,
          minimum: null,
          maximum: null,
        },
      ],
      row_count: 3,
    };
    render(
      <ThemeProvider theme={theme}>
        <FeatureStatisticsPanel statistics={statistics} />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('renders nothing when there are no columns', () => {
    const statistics: FeatureStatistics = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      columns: [],
      row_count: 0,
    };
    const { container } = render(
      <ThemeProvider theme={theme}>
        <FeatureStatisticsPanel statistics={statistics} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
