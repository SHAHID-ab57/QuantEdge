import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { MetricMetadata } from '@/types/api/evaluation';
import { MetricCatalogPanel } from './metric-catalog-panel';

const METRICS: MetricMetadata[] = [
  {
    name: 'accuracy',
    label: 'Accuracy',
    description: 'Overall fraction correct.',
    category: 'classification',
    higher_is_better: true,
    requires_probabilities: false,
    version: '1.0.0',
  },
  {
    name: 'rmse',
    label: 'RMSE',
    description: 'Root mean squared error.',
    category: 'regression',
    higher_is_better: false,
    requires_probabilities: false,
    version: '1.0.0',
  },
];

afterEach(() => cleanup());

describe('MetricCatalogPanel', () => {
  it('groups metrics into classification and regression sections', () => {
    render(
      <ThemeProvider theme={theme}>
        <MetricCatalogPanel metrics={METRICS} />
      </ThemeProvider>,
    );
    expect(screen.getByText('Classification metrics')).toBeInTheDocument();
    expect(screen.getByText('Regression metrics')).toBeInTheDocument();
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
    expect(screen.getByText('RMSE')).toBeInTheDocument();
  });
});
