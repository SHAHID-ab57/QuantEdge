import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import * as trainingApi from '@/lib/api/training';
import type { TrainingJobListResponse } from '@/types/api/training';
import { PredictionForm } from './prediction-form';

vi.mock('@/lib/api/training', () => ({
  fetchTrainingJobs: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
}));

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

function renderForm(onSubmit = vi.fn(), submitting = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <PredictionForm onSubmit={onSubmit} submitting={submitting} />
    </QueryClientProvider>,
  );
  return { ...utils, onSubmit };
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
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PredictionForm', () => {
  it('only requests completed training jobs', async () => {
    renderForm();
    await waitFor(() =>
      expect(mockedTrainingApi.fetchTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'completed' }),
      ),
    );
  });

  it('keeps Run Prediction disabled until a job and a symbol are both chosen', async () => {
    renderForm();
    await screen.findByLabelText('Training job');

    expect(screen.getByRole('button', { name: 'Run Prediction' })).toBeDisabled();

    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(await screen.findByRole('option', { name: /logistic_regression/ }));
    expect(screen.getByRole('button', { name: 'Run Prediction' })).toBeDisabled();

    fireEvent.mouseDown(screen.getByLabelText('Symbol'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    expect(screen.getByRole('button', { name: 'Run Prediction' })).not.toBeDisabled();
  });

  it('submits the selected job id and symbol, with no as_of when left blank', async () => {
    const { onSubmit } = renderForm();
    await screen.findByLabelText('Training job');

    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(await screen.findByRole('option', { name: /logistic_regression/ }));
    fireEvent.mouseDown(screen.getByLabelText('Symbol'));
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.click(screen.getByRole('button', { name: 'Run Prediction' }));

    expect(onSubmit).toHaveBeenCalledWith({
      trainingJobId: 'job-1',
      symbol: 'ETHUSD',
      asOf: null,
    });
  });

  it('shows an empty-state notice when there are no completed training jobs', async () => {
    mockedTrainingApi.fetchTrainingJobs.mockResolvedValue({
      ...jobListResponse(),
      jobs: [],
      total: 0,
    });
    renderForm();

    expect(
      await screen.findByText(
        'No completed training jobs yet — train and run one on the ML Training page first.',
      ),
    ).toBeInTheDocument();
  });

  it('shows "Predicting…" while submitting', async () => {
    renderForm(vi.fn(), true);
    expect(await screen.findByRole('button', { name: 'Predicting…' })).toBeDisabled();
  });
});
