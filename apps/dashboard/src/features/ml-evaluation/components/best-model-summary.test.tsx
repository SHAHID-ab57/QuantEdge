import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { BenchmarkBestEntry } from '@/types/api/evaluation';
import { BestModelSummary } from './best-model-summary';

afterEach(() => cleanup());

describe('BestModelSummary', () => {
  it('renders one card per metric with the winning model and value', () => {
    const entries: BenchmarkBestEntry[] = [
      {
        metric: 'accuracy',
        training_job_id: 'job-b',
        model_type: 'logistic_regression',
        value: 0.9,
        higher_is_better: true,
      },
      {
        metric: 'rmse',
        training_job_id: 'job-c',
        model_type: 'linear_regression',
        value: 1.2,
        higher_is_better: false,
      },
    ];
    render(
      <ThemeProvider theme={theme}>
        <BestModelSummary bestByMetric={entries} />
      </ThemeProvider>,
    );
    expect(screen.getByText('accuracy')).toBeInTheDocument();
    expect(screen.getByText('rmse')).toBeInTheDocument();
    expect(screen.getByText('0.9000')).toBeInTheDocument();
    expect(screen.getByText('1.2000')).toBeInTheDocument();
    expect(screen.getByText('logistic_regression')).toBeInTheDocument();
    expect(screen.getByText('linear_regression')).toBeInTheDocument();
  });

  it('renders nothing when there is nothing to summarize', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <BestModelSummary bestByMetric={[]} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
