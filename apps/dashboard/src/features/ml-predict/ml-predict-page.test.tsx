import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as predictionApi from '@/lib/api/prediction';
import * as trainingApi from '@/lib/api/training';
import type { PredictionListResponse, PredictionResponse } from '@/types/api/prediction';
import type { TrainingJobListResponse } from '@/types/api/training';
import { MLPredictPage } from './ml-predict-page';

vi.mock('@/lib/api/prediction', () => ({
  runPrediction: vi.fn(),
  fetchPrediction: vi.fn(),
  fetchPredictions: vi.fn(),
}));

vi.mock('@/lib/api/training', () => ({
  fetchTrainingJobs: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
}));

const mockedPredictionApi = vi.mocked(predictionApi);
const mockedTrainingApi = vi.mocked(trainingApi);
const mockedMarketApi = vi.mocked(marketApi);

function jobListResponse(): TrainingJobListResponse {
  return {
    jobs: [
      {
        id: 'job-1',
        experiment_id: 'exp-1',
        dataset_version: 'ds-abc',
        model_type: 'logistic_regression',
        status: 'completed',
        current_stage: 'update_experiment',
        log_count: 3,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    total: 1,
    limit: 200,
    offset: 0,
    statuses: ['pending', 'running', 'completed', 'failed', 'cancelled'],
    stages: [
      'validate_dataset',
      'load_dataset',
      'initialize_model',
      'execute_training',
      'save_results',
      'update_experiment',
    ],
  };
}

function predictionResponse(overrides: Partial<PredictionResponse> = {}): PredictionResponse {
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
    confidence: 0.8,
    confidence_unavailable_reason: null,
    probabilities: { down: 0.2, up: 0.8 },
    classes: ['down', 'up'],
    feature_columns: ['open', 'high', 'low', 'close', 'volume'],
    actual_outcome: null,
    created_at: '2026-01-05T12:05:00Z',
    ...overrides,
  };
}

function historyResponse(overrides: Partial<PredictionListResponse> = {}): PredictionListResponse {
  return {
    predictions: [],
    total: 0,
    limit: 10,
    offset: 0,
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MLPredictPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedTrainingApi.fetchTrainingJobs.mockResolvedValue(jobListResponse());
  mockedMarketApi.fetchMarkets.mockResolvedValue({
    markets: [
      {
        id: 'market-1',
        symbol: 'ETHUSD',
        exchange: 'Delta Exchange',
        exchange_id: '11111111-1111-4111-8111-111111111111',
        base_asset: 'ETH',
        quote_asset: 'USD',
        market_type: 'perpetual',
        is_active: true,
        delta_product_id: null,
        delta_contract_type: null,
        tick_size: null,
        funding_method: null,
        funding_interval_seconds: null,
        listing_date: null,
      },
    ],
    total: 1,
  });
  mockedPredictionApi.fetchPredictions.mockResolvedValue(historyResponse());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('MLPredictPage', () => {
  it('runs a prediction and shows the result panel', async () => {
    mockedPredictionApi.runPrediction.mockResolvedValue(predictionResponse());
    renderPage();
    await screen.findByLabelText('Training job');

    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(await screen.findByRole('option', { name: /logistic_regression/ }));
    fireEvent.mouseDown(screen.getByLabelText('Symbol'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Prediction' }));

    await waitFor(() =>
      expect(mockedPredictionApi.runPrediction).toHaveBeenCalledWith({
        training_job_id: 'job-1',
        symbol: 'ETHUSD',
      }),
    );
    expect(await screen.findByLabelText('Prediction result')).toBeInTheDocument();
    expect(screen.getByText('next_direction_1')).toBeInTheDocument();
  });

  it('surfaces a run error', async () => {
    mockedPredictionApi.runPrediction.mockRejectedValue(new Error('backend down'));
    renderPage();
    await screen.findByLabelText('Training job');

    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(await screen.findByRole('option', { name: /logistic_regression/ }));
    fireEvent.mouseDown(screen.getByLabelText('Symbol'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Prediction' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('backend down');
  });

  it('reopens a prediction from Prediction History', async () => {
    mockedPredictionApi.fetchPredictions.mockResolvedValue(
      historyResponse({
        predictions: [
          {
            id: 'pred-2',
            training_job_id: 'job-1',
            experiment_id: 'exp-1',
            symbol: 'BTCUSD',
            timeframe: '1h',
            model_type: 'logistic_regression',
            model_kind: 'classification',
            target_column: 'next_direction_1',
            horizon: 1,
            as_of: '2026-01-04T12:00:00Z',
            predicted_value: 'down',
            confidence: 0.6,
            created_at: '2026-01-04T12:05:00Z',
          },
        ],
        total: 1,
      }),
    );
    mockedPredictionApi.fetchPrediction.mockResolvedValue(
      predictionResponse({ id: 'pred-2', symbol: 'BTCUSD', predicted_value: 'down' }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Reopen prediction pred-2' }));

    await waitFor(() => expect(mockedPredictionApi.fetchPrediction).toHaveBeenCalledWith('pred-2'));
    expect(await screen.findByLabelText('Prediction result')).toBeInTheDocument();
  });
});
