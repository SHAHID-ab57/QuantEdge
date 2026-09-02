import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { PredictionResponse } from '@/types/api/prediction';
import { PredictionResultPanel } from './prediction-result-panel';

function prediction(overrides: Partial<PredictionResponse> = {}): PredictionResponse {
  return {
    id: 'pred-1',
    training_job_id: 'job-1',
    experiment_id: 'exp-1',
    symbol: 'ETHUSD',
    timeframe: '1h',
    model_type: 'logistic_regression',
    model_kind: 'classification',
    target_column: 'next_direction_1',
    horizon: 1,
    as_of: '2026-01-05T12:00:00Z',
    predicted_value: 'up',
    confidence: 0.8123,
    confidence_unavailable_reason: null,
    probabilities: { down: 0.1877, up: 0.8123 },
    classes: ['down', 'up'],
    feature_columns: ['open', 'high', 'low', 'close', 'volume'],
    actual_outcome: null,
    is_correct: null,
    error: null,
    graded_at: null,
    available_after: '2026-01-05T13:00:00Z',
    created_at: '2026-01-05T12:05:00Z',
    ...overrides,
  };
}

afterEach(() => cleanup());

describe('PredictionResultPanel', () => {
  it('leads with target and horizon, then the predicted value', () => {
    render(<PredictionResultPanel prediction={prediction()} />);

    expect(screen.getByText('next_direction_1')).toBeInTheDocument();
    expect(screen.getByText('1 candle(s) ahead')).toBeInTheDocument();
    expect(screen.getByText('up')).toBeInTheDocument();
  });

  it('frames confidence explicitly as a probability', () => {
    render(<PredictionResultPanel prediction={prediction({ confidence: 0.8123 })} />);
    expect(screen.getByText('81.2% probability')).toBeInTheDocument();
  });

  it('shows every class’s own probability, highlighting the predicted one', () => {
    render(<PredictionResultPanel prediction={prediction()} />);
    expect(screen.getByText('up: 81.2%')).toBeInTheDocument();
    expect(screen.getByText('down: 18.8%')).toBeInTheDocument();
  });

  it('states plainly when confidence is unavailable, rather than hiding the field', () => {
    render(
      <PredictionResultPanel
        prediction={prediction({
          confidence: null,
          confidence_unavailable_reason: 'This model does not produce class probabilities.',
          probabilities: null,
          classes: null,
        })}
      />,
    );

    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(screen.queryByText(/probability$/)).not.toBeInTheDocument();
  });

  it('reports actual_outcome as not graded yet when null', () => {
    render(<PredictionResultPanel prediction={prediction({ actual_outcome: null })} />);
    expect(screen.getByText('Not graded yet')).toBeInTheDocument();
  });

  it('links to the source experiment and training job', () => {
    render(<PredictionResultPanel prediction={prediction()} />);

    expect(screen.getByRole('link', { name: 'View experiment' })).toHaveAttribute(
      'href',
      '/experiments/exp-1',
    );
    expect(screen.getByRole('link', { name: 'View training job' })).toHaveAttribute(
      'href',
      '/ml/training?jobId=job-1',
    );
  });

  it('renders a numeric predicted value for a regressor with no confidence row content', () => {
    render(
      <PredictionResultPanel
        prediction={prediction({
          model_kind: 'regression',
          target_column: 'next_close_1',
          predicted_value: 1234.5,
          confidence: null,
          confidence_unavailable_reason: 'This model does not produce class probabilities.',
          probabilities: null,
          classes: null,
        })}
      />,
    );

    expect(screen.getByText('1234.5')).toBeInTheDocument();
    expect(screen.getByText('Not available')).toBeInTheDocument();
  });
});
