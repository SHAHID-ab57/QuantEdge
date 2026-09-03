import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as backtestApi from '@/lib/api/backtest';
import * as marketApi from '@/lib/api/market';
import * as predictionApi from '@/lib/api/prediction';
import * as trainingApi from '@/lib/api/training';
import type { BacktestListResponse, BacktestRun } from '@/types/api/backtest';
import type { PredictionListResponse } from '@/types/api/prediction';
import type { TrainingJobListResponse } from '@/types/api/training';
import { MLBacktestPage } from './ml-backtest-page';

vi.mock('@/lib/api/backtest', () => ({
  runBacktest: vi.fn(),
  fetchBacktest: vi.fn(),
  fetchBacktests: vi.fn(),
}));

vi.mock('@/lib/api/training', () => ({
  fetchTrainingJobs: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
}));

vi.mock('@/lib/api/prediction', () => ({
  runPrediction: vi.fn(),
  fetchPrediction: vi.fn(),
  fetchPredictions: vi.fn(),
}));

const mockedBacktestApi = vi.mocked(backtestApi);
const mockedTrainingApi = vi.mocked(trainingApi);
const mockedMarketApi = vi.mocked(marketApi);
const mockedPredictionApi = vi.mocked(predictionApi);

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

function backtestRun(overrides: Partial<BacktestRun> = {}): BacktestRun {
  return {
    id: 'run-1',
    training_job_id: 'job-1',
    experiment_id: 'exp-1',
    symbol: 'ETHUSD',
    timeframe: '1h',
    step: '1h',
    requested_start: '2026-01-01T00:00:00Z',
    requested_end: '2026-01-01T05:00:00Z',
    effective_end: '2026-01-01T05:00:00Z',
    truncated: false,
    status: 'completed',
    error_message: null,
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:00:05Z',
    total_steps: 5,
    completed_steps: 5,
    graded_count: 5,
    model_kind: 'classification',
    aggregate_metrics: { accuracy: 0.8 },
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function backtestListResponse(overrides: Partial<BacktestListResponse> = {}): BacktestListResponse {
  return { runs: [], total: 0, limit: 10, offset: 0, ...overrides };
}

function predictionHistoryResponse(
  overrides: Partial<PredictionListResponse> = {},
): PredictionListResponse {
  return { predictions: [], total: 0, limit: 10, offset: 0, ...overrides };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MLBacktestPage />
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
  mockedBacktestApi.fetchBacktests.mockResolvedValue(backtestListResponse());
  mockedPredictionApi.fetchPredictions.mockResolvedValue(predictionHistoryResponse());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function fillAndSubmit() {
  await screen.findByLabelText('Training job');
  fireEvent.mouseDown(screen.getByLabelText('Training job'));
  fireEvent.click(await screen.findByRole('option', { name: /logistic_regression/ }));
  fireEvent.mouseDown(screen.getByLabelText('Symbol'));
  fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
  fireEvent.change(screen.getByLabelText('Start'), { target: { value: '2026-01-01T00:00' } });
  fireEvent.change(screen.getByLabelText('End'), { target: { value: '2026-01-01T05:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));
}

describe('MLBacktestPage', () => {
  it('runs a backtest and shows the result panel with aggregate metrics', async () => {
    mockedBacktestApi.runBacktest.mockResolvedValue(backtestRun());
    renderPage();

    await fillAndSubmit();

    await waitFor(() =>
      expect(mockedBacktestApi.runBacktest).toHaveBeenCalledWith({
        training_job_id: 'job-1',
        symbol: 'ETHUSD',
        start: new Date('2026-01-01T00:00').toISOString(),
        end: new Date('2026-01-01T05:00').toISOString(),
      }),
    );
    expect(await screen.findByLabelText('Backtest result')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('5/5 steps · 5 graded')).toBeInTheDocument();
  });

  it('surfaces a run error', async () => {
    mockedBacktestApi.runBacktest.mockRejectedValue(new Error('backend down'));
    renderPage();

    await fillAndSubmit();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('backend down');
  });

  it('reports truncation honestly when the run was capped', async () => {
    mockedBacktestApi.runBacktest.mockResolvedValue(
      backtestRun({ truncated: true, total_steps: 3, completed_steps: 3, graded_count: 3 }),
    );
    renderPage();

    await fillAndSubmit();

    expect(
      await screen.findByText(/needed more steps than this platform allows/),
    ).toBeInTheDocument();
  });

  it('reopens a backtest from Backtest History and drills down into its predictions', async () => {
    mockedBacktestApi.fetchBacktests.mockResolvedValue(
      backtestListResponse({
        runs: [
          {
            id: 'run-2',
            training_job_id: 'job-1',
            symbol: 'BTCUSD',
            timeframe: '1h',
            step: '1h',
            status: 'completed',
            truncated: false,
            total_steps: 2,
            completed_steps: 2,
            graded_count: 2,
            created_at: '2026-01-02T00:00:00Z',
            completed_at: '2026-01-02T00:00:05Z',
          },
        ],
        total: 1,
      }),
    );
    mockedBacktestApi.fetchBacktest.mockResolvedValue(
      backtestRun({ id: 'run-2', symbol: 'BTCUSD' }),
    );
    mockedPredictionApi.fetchPredictions.mockResolvedValue(
      predictionHistoryResponse({
        predictions: [
          {
            id: 'pred-1',
            training_job_id: 'job-1',
            experiment_id: 'exp-1',
            symbol: 'BTCUSD',
            timeframe: '1h',
            model_type: 'logistic_regression',
            model_kind: 'classification',
            target_column: 'next_direction_1',
            horizon: 1,
            as_of: '2026-01-02T00:00:00Z',
            predicted_value: 'up',
            confidence: 0.7,
            actual_outcome: 'up',
            is_correct: true,
            error: null,
            graded_at: '2026-01-02T01:00:00Z',
            available_after: null,
            created_at: '2026-01-02T00:00:05Z',
          },
        ],
        total: 1,
      }),
    );

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Reopen backtest run-2' }));

    await waitFor(() => expect(mockedBacktestApi.fetchBacktest).toHaveBeenCalledWith('run-2'));
    expect(await screen.findByLabelText('Backtest result')).toBeInTheDocument();

    await waitFor(() =>
      expect(mockedPredictionApi.fetchPredictions).toHaveBeenCalledWith(
        expect.objectContaining({ backtest_run_id: 'run-2' }),
      ),
    );
    expect(await screen.findByText('next_direction_1')).toBeInTheDocument();
  });
});
