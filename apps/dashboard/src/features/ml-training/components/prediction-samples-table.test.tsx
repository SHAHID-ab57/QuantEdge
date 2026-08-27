import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { PredictionSamplesTable } from './prediction-samples-table';

afterEach(() => cleanup());

describe('PredictionSamplesTable', () => {
  it('renders probability, confidence, and correctness for a classification sample', () => {
    render(
      <ThemeProvider theme={theme}>
        <PredictionSamplesTable
          samples={[
            {
              actual: 'up',
              predicted: 'up',
              probability: 0.91,
              confidence_level: 'high',
              correct: true,
            },
            {
              actual: 'down',
              predicted: 'up',
              probability: 0.55,
              confidence_level: 'medium',
              correct: false,
            },
          ]}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Probability')).toBeInTheDocument();
    expect(screen.getByText('0.910')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByLabelText('Correct')).toBeInTheDocument();
    expect(screen.getByLabelText('Incorrect')).toBeInTheDocument();
  });

  it('omits probability/confidence/correctness columns for a regression sample', () => {
    render(
      <ThemeProvider theme={theme}>
        <PredictionSamplesTable
          samples={[
            {
              actual: 100.5,
              predicted: 101.2,
              probability: null,
              confidence_level: null,
              correct: null,
            },
          ]}
        />
      </ThemeProvider>,
    );
    expect(screen.queryByText('Probability')).not.toBeInTheDocument();
    expect(screen.queryByText('Confidence')).not.toBeInTheDocument();
    expect(screen.getByText('100.5000')).toBeInTheDocument();
  });

  it('renders nothing for a malformed or empty samples value', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <PredictionSamplesTable samples={undefined} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
