import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureCorrelation } from '@/types/api/features';
import { FeatureCorrelationMatrix } from './feature-correlation-matrix';

afterEach(() => cleanup());

describe('FeatureCorrelationMatrix', () => {
  it('renders a header per column and the diagonal as 1.00', () => {
    const correlation: FeatureCorrelation = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      columns: ['open', 'volume'],
      matrix: [
        [1.0, 1.0],
        [1.0, 1.0],
      ],
      row_count: 3,
    };
    render(
      <ThemeProvider theme={theme}>
        <FeatureCorrelationMatrix correlation={correlation} />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('open').length).toBeGreaterThan(0);
    expect(screen.getAllByText('volume').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1.00').length).toBe(4);
    expect(screen.getByText('3 rows compared')).toBeInTheDocument();
  });

  it('renders nothing with fewer than two columns', () => {
    const correlation: FeatureCorrelation = {
      symbol: 'ETHUSD',
      timeframe: '1h',
      columns: [],
      matrix: [],
      row_count: 0,
    };
    const { container } = render(
      <ThemeProvider theme={theme}>
        <FeatureCorrelationMatrix correlation={correlation} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
