import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { ConfusionMatrixDetailsTable } from './confusion-matrix-details-table';

afterEach(() => cleanup());

describe('ConfusionMatrixDetailsTable', () => {
  it('renders per-class TP/FP/TN/FN/support', () => {
    render(
      <ThemeProvider theme={theme}>
        <ConfusionMatrixDetailsTable
          details={[
            {
              class: 'up',
              true_positive: 5,
              false_positive: 1,
              true_negative: 8,
              false_negative: 2,
              support: 7,
            },
          ]}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Confusion Matrix Details')).toBeInTheDocument();
    expect(screen.getByText('up')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('renders nothing for a malformed or empty details value', () => {
    const { container } = render(
      <ThemeProvider theme={theme}>
        <ConfusionMatrixDetailsTable details={null} />
      </ThemeProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
