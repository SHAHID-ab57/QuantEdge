import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import { EvaluationSummary } from './evaluation-summary';

afterEach(() => cleanup());

describe('EvaluationSummary — classification', () => {
  it('renders classification metrics', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary
          modelKind="classification"
          metrics={{ accuracy: 0.9123, precision: 0.8, recall: 0.75, f1: 0.774 }}
          summary={{}}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
    // The Train/Validation/Test table below also renders the validation column
    // with this same value, so more than one match is expected here.
    expect(screen.getAllByText('0.9123').length).toBeGreaterThan(0);
    expect(screen.getByText('Precision')).toBeInTheDocument();
    expect(screen.getByText('Recall')).toBeInTheDocument();
    expect(screen.getByText('F1')).toBeInTheDocument();
  });

  it('renders a confusion matrix when classes and a matrix are present', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary
          modelKind="classification"
          metrics={{ accuracy: 1 }}
          summary={{
            classes: ['down', 'up'],
            confusion_matrix: [
              [5, 1],
              [0, 6],
            ],
          }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Confusion Matrix')).toBeInTheDocument();
    expect(screen.getAllByText('down').length).toBeGreaterThan(0);
    expect(screen.getAllByText('up').length).toBeGreaterThan(0);
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
  });

  it('omits the confusion matrix when it is missing from the summary', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary modelKind="classification" metrics={{ accuracy: 1 }} summary={{}} />
      </ThemeProvider>,
    );
    expect(screen.queryByText('Confusion Matrix')).not.toBeInTheDocument();
  });
});

describe('EvaluationSummary — regression', () => {
  it('renders regression metrics', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary
          modelKind="regression"
          metrics={{ mae: 1.2345, mse: 2.5, rmse: 1.581, r2: 0.987 }}
          summary={{}}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('MAE')).toBeInTheDocument();
    // The Train/Validation/Test table below also renders the validation column
    // with this same value, so more than one match is expected here.
    expect(screen.getAllByText('1.2345').length).toBeGreaterThan(0);
    expect(screen.getByText('MSE')).toBeInTheDocument();
    expect(screen.getByText('RMSE')).toBeInTheDocument();
    expect(screen.getByText('R²')).toBeInTheDocument();
  });
});

describe('EvaluationSummary — placeholder / unknown', () => {
  it('falls back to a generic metrics list', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary
          modelKind="placeholder"
          metrics={{ placeholder_loss: 0.1, placeholder_accuracy: 0.9 }}
          summary={{}}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText(/placeholder_loss: 0.1/)).toBeInTheDocument();
    expect(screen.getByText(/placeholder_accuracy: 0.9/)).toBeInTheDocument();
  });

  it('falls back to a generic metrics list when model_kind is unknown', () => {
    render(
      <ThemeProvider theme={theme}>
        <EvaluationSummary modelKind={undefined} metrics={{ some_metric: 42 }} summary={{}} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/some_metric: 42/)).toBeInTheDocument();
  });
});
