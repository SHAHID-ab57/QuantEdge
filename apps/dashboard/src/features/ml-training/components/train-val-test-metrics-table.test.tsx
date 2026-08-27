import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { TrainValTestMetricsTable } from './train-val-test-metrics-table';

afterEach(() => cleanup());

describe('TrainValTestMetricsTable', () => {
  it('renders train, validation, and test columns', () => {
    render(
      <ThemeProvider theme={theme}>
        <TrainValTestMetricsTable
          trainMetrics={{ accuracy: 0.99 }}
          validationMetrics={{ accuracy: 0.8 }}
          testMetrics={{ accuracy: 0.78 }}
          overfitting={{
            flagged: false,
            gap: 0.01,
            threshold: 0.15,
            message: 'No significant gap.',
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('0.9900')).toBeInTheDocument();
    expect(screen.getByText('0.8000')).toBeInTheDocument();
    expect(screen.getByText('0.7800')).toBeInTheDocument();
    expect(screen.getByText('No significant gap.')).toBeInTheDocument();
  });

  it('shows a warning banner when overfitting is flagged', () => {
    render(
      <ThemeProvider theme={theme}>
        <TrainValTestMetricsTable
          trainMetrics={{ accuracy: 0.99 }}
          validationMetrics={{ accuracy: 0.5 }}
          testMetrics={{}}
          overfitting={{
            flagged: true,
            gap: 0.49,
            threshold: 0.15,
            message: 'Possible overfitting.',
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Possible overfitting.')).toBeInTheDocument();
  });

  it('renders an empty test column when the test split had no rows', () => {
    render(
      <ThemeProvider theme={theme}>
        <TrainValTestMetricsTable
          trainMetrics={{ mae: 1 }}
          validationMetrics={{ mae: 1.1 }}
          testMetrics={{}}
          overfitting={null}
        />
      </ThemeProvider>,
    );
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('renders nothing when no metrics are present at all', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <TrainValTestMetricsTable
          trainMetrics={undefined}
          validationMetrics={undefined}
          testMetrics={undefined}
          overfitting={undefined}
        />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
