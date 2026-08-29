import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experimentsApi from '@/lib/api/experiments';
import * as marketApi from '@/lib/api/market';
import * as trainingApi from '@/lib/api/training';
import type { Experiment, ExperimentListResponse } from '@/types/api/experiments';
import type {
  ModelAdapterCatalogResponse,
  TrainingJob,
  TrainingJobListResponse,
} from '@/types/api/training';
import { MLTrainingPage } from './ml-training-page';

vi.mock('@/lib/api/experiments', () => ({
  fetchExperiments: vi.fn(),
  fetchExperiment: vi.fn(),
}));

vi.mock('@/lib/api/training', () => ({
  fetchTrainingJobs: vi.fn(),
  fetchTrainingJob: vi.fn(),
  createTrainingJob: vi.fn(),
  deleteTrainingJob: vi.fn(),
  runTrainingJob: vi.fn(),
  cancelTrainingJob: vi.fn(),
  fetchModelAdapters: vi.fn(),
  fetchTrainingArtifacts: vi.fn(),
  downloadTrainingArtifact: vi.fn(),
}));

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
}));

let searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

const mockedExperimentsApi = vi.mocked(experimentsApi);
const mockedTrainingApi = vi.mocked(trainingApi);
const mockedMarketApi = vi.mocked(marketApi);

function experimentListResponse(
  overrides: Partial<ExperimentListResponse> = {},
): ExperimentListResponse {
  return {
    experiments: [
      {
        id: 'exp-1',
        name: 'Baseline SMA',
        dataset_version: 'ds-abc',
        model_type: 'xgboost',
        status: 'draft',
        tags: [],
        metric_count: 0,
        artifact_count: 0,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    total: 1,
    limit: 200,
    offset: 0,
    statuses: ['draft', 'running', 'completed', 'failed', 'archived'],
    artifact_types: ['dataset_export', 'model_checkpoint', 'report', 'plot', 'other'],
    ...overrides,
  };
}

function experimentDetail(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: 'exp-1',
    name: 'Baseline SMA',
    dataset_version: 'ds-abc',
    feature_set: [{ feature: 'sma', params: { period: '20' } }],
    target_config: [{ target: 'next_close', params: { horizon: '1' } }],
    split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    model_type: 'xgboost',
    status: 'draft',
    notes: null,
    tags: [],
    metrics: [],
    artifacts: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function jobSummary(overrides: Partial<TrainingJob> = {}) {
  return {
    id: 'job-1',
    experiment_id: 'exp-1',
    dataset_version: 'ds-abc',
    model_type: 'placeholder',
    status: 'pending' as const,
    current_stage: null,
    log_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function jobDetail(overrides: Partial<TrainingJob> = {}): TrainingJob {
  return {
    id: 'job-1',
    experiment_id: 'exp-1',
    dataset_version: 'ds-abc',
    symbol: null,
    timeframe: null,
    target_column: null,
    model_type: 'placeholder',
    hyperparameters: {},
    status: 'pending',
    current_stage: null,
    error_message: null,
    result_summary: null,
    started_at: null,
    completed_at: null,
    logs: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function listResponse(overrides: Partial<TrainingJobListResponse> = {}): TrainingJobListResponse {
  return {
    jobs: [jobSummary()],
    total: 1,
    limit: 20,
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
    ...overrides,
  };
}

function modelAdapters(): ModelAdapterCatalogResponse {
  return {
    adapters: [
      {
        name: 'placeholder',
        label: 'Placeholder Model',
        description: 'Fabricates deterministic metrics.',
        framework: 'placeholder',
        model_kind: 'placeholder',
        requires_real_data: false,
        hyperparameter_hints: ['epochs', 'learning_rate'],
        version: '1.0.0',
      },
      {
        name: 'logistic_regression',
        label: 'Logistic Regression (Baseline)',
        description: 'A scikit-learn LogisticRegression baseline classifier.',
        framework: 'scikit-learn',
        model_kind: 'classification',
        requires_real_data: true,
        hyperparameter_hints: ['max_iter', 'C', 'random_seed'],
        version: '1.0.0',
      },
      {
        name: 'linear_regression',
        label: 'Linear Regression (Baseline)',
        description: 'A scikit-learn LinearRegression baseline regressor.',
        framework: 'scikit-learn',
        model_kind: 'regression',
        requires_real_data: true,
        hyperparameter_hints: ['fit_intercept'],
        version: '1.0.0',
      },
    ],
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MLTrainingPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  searchParams = new URLSearchParams();
  mockedTrainingApi.fetchTrainingJobs.mockResolvedValue(listResponse());
  mockedTrainingApi.fetchModelAdapters.mockResolvedValue(modelAdapters());
  mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({ job_id: 'job-1', artifacts: [] });
  mockedExperimentsApi.fetchExperiments.mockResolvedValue(experimentListResponse());
  mockedExperimentsApi.fetchExperiment.mockResolvedValue(experimentDetail());
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
  mockedMarketApi.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1h', '1d'] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('MLTrainingPage — listing', () => {
  it('lists training jobs returned by the backend', async () => {
    renderPage();
    expect(await screen.findByText('placeholder')).toBeInTheDocument();
  });

  it('shows a loading skeleton before the first page arrives', () => {
    mockedTrainingApi.fetchTrainingJobs.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });

  it('surfaces a load error with a retry action', async () => {
    mockedTrainingApi.fetchTrainingJobs.mockRejectedValue(new Error('backend down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('backend down');
  });

  it('reports an empty result', async () => {
    mockedTrainingApi.fetchTrainingJobs.mockResolvedValue(listResponse({ jobs: [], total: 0 }));
    renderPage();
    expect(await screen.findByText('No training jobs match this filter.')).toBeInTheDocument();
  });

  it('explains that no experiments exist yet when there are none at all', async () => {
    mockedTrainingApi.fetchTrainingJobs.mockResolvedValue(listResponse({ jobs: [], total: 0 }));
    mockedExperimentsApi.fetchExperiments.mockResolvedValue(
      experimentListResponse({ experiments: [], total: 0 }),
    );
    renderPage();
    expect(
      await screen.findByText(
        'No experiments exist yet — create one before registering a training job.',
      ),
    ).toBeInTheDocument();
  });
});

describe('MLTrainingPage — filtering and sorting', () => {
  it('sends the selected experiment as the experiment_id parameter', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.mouseDown(screen.getByLabelText('Experiment'));
    fireEvent.click(screen.getByRole('option', { name: 'Baseline SMA' }));

    await waitFor(() =>
      expect(mockedTrainingApi.fetchTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ experiment_id: 'exp-1' }),
      ),
    );
  });

  it('sends the selected status as the status parameter', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(screen.getByRole('option', { name: 'Running' }));

    await waitFor(() =>
      expect(mockedTrainingApi.fetchTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'running' }),
      ),
    );
  });

  it('toggles sort direction when the same column header is clicked twice', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'Model Type' }));

    await waitFor(() =>
      expect(mockedTrainingApi.fetchTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'model_type', dir: 'asc' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Model Type' }));
    await waitFor(() =>
      expect(mockedTrainingApi.fetchTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'model_type', dir: 'desc' }),
      ),
    );
  });
});

describe('MLTrainingPage — creating a training job', () => {
  it('opens the create dialog with the experiment and model adapter selectors', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    expect(screen.getByText('Register a New Training Job')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Experiment')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Model type')).toBeInTheDocument();
  });

  it('cannot submit without selecting an experiment', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    expect(screen.getByRole('button', { name: 'Create Training Job' })).toBeDisabled();
  });

  it('explains why the form cannot be submitted yet', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));

    // The one registered model adapter is auto-selected, so only the
    // experiment/dataset reasons apply until an experiment is chosen.
    expect(screen.getByText('Select an experiment.')).toBeInTheDocument();
    expect(screen.getByText('Enter or select a dataset version.')).toBeInTheDocument();
  });

  it('explains a missing model type when no adapter can be auto-selected', async () => {
    mockedTrainingApi.fetchModelAdapters.mockResolvedValue({ adapters: [] });
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));

    expect(await screen.findByText('Select a model type.')).toBeInTheDocument();
  });

  it('stops explaining once every required field is filled', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByLabelText('Experiment');
    fireEvent.mouseDown(within(dialog).getByLabelText('Experiment'));
    fireEvent.click(await screen.findByRole('option', { name: 'Baseline SMA' }));

    await waitFor(() =>
      expect(screen.queryByText('Select an experiment.')).not.toBeInTheDocument(),
    );
    expect(screen.queryByText('Enter or select a dataset version.')).not.toBeInTheDocument();
    expect(screen.queryByText('Select a model type.')).not.toBeInTheDocument();
  });

  it('shows an empty-state notice and blocks the model field when no adapters are registered', async () => {
    mockedTrainingApi.fetchModelAdapters.mockResolvedValue({ adapters: [] });
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));

    expect(await screen.findByText('No model adapters registered')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByLabelText('Model type')).toBeDisabled();
  });

  it('shows an empty-state notice when no experiment has a recorded dataset version', async () => {
    mockedExperimentsApi.fetchExperiments.mockResolvedValue(
      experimentListResponse({
        experiments: [
          {
            id: 'exp-2',
            name: 'No dataset yet',
            dataset_version: null,
            model_type: null,
            status: 'draft',
            tags: [],
            metric_count: 0,
            artifact_count: 0,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    );
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));

    expect(await screen.findByText('No datasets available')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Build a dataset' });
    expect(link).toHaveAttribute('href', '/ml-datasets');
  });

  it('creates a training job and opens its detail dialog', async () => {
    mockedTrainingApi.createTrainingJob.mockResolvedValue(jobDetail({ id: 'job-2' }));
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail({ id: 'job-2' }));
    renderPage();
    await screen.findByText('placeholder');

    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByLabelText('Experiment');
    fireEvent.mouseDown(within(dialog).getByLabelText('Experiment'));
    fireEvent.click(await screen.findByRole('option', { name: 'Baseline SMA' }));

    await waitFor(() =>
      expect(within(dialog).getByLabelText('Model type')).toHaveValue('Placeholder Model'),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Create Training Job' }));

    await waitFor(() =>
      expect(mockedTrainingApi.createTrainingJob).toHaveBeenCalledWith({
        experiment_id: 'exp-1',
        model_type: 'placeholder',
        dataset_version: 'ds-abc',
        symbol: null,
        timeframe: null,
        target_column: null,
        hyperparameters: {
          epochs: 10,
          learning_rate: 0.001,
          batch_size: 32,
          random_seed: 42,
          validation_frequency: 1,
        },
      }),
    );
    expect(await screen.findByText('Training Job')).toBeInTheDocument();
  });

  it('reveals the configuration panel only for a model adapter that requires real data', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');

    expect(within(dialog).queryByLabelText('Symbol')).not.toBeInTheDocument();

    fireEvent.mouseDown(within(dialog).getByLabelText('Model type'));
    fireEvent.click(await screen.findByRole('option', { name: 'Logistic Regression (Baseline)' }));

    expect(await within(dialog).findByLabelText('Symbol')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Timeframe')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Target column')).toBeInTheDocument();
  });

  it('requires a symbol and timeframe for a model adapter that requires real data', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText('Model type'));
    fireEvent.click(await screen.findByRole('option', { name: 'Logistic Regression (Baseline)' }));

    expect(await screen.findByText('Select a market symbol.')).toBeInTheDocument();
    expect(screen.getByText('Select a timeframe.')).toBeInTheDocument();
  });

  it('populates the timeframe options once a symbol is selected', async () => {
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByLabelText('Model type'));
    fireEvent.click(await screen.findByRole('option', { name: 'Logistic Regression (Baseline)' }));
    const symbolField = await within(dialog).findByLabelText('Symbol');
    fireEvent.mouseDown(symbolField);
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));

    fireEvent.mouseDown(within(dialog).getByLabelText('Timeframe'));
    expect(await screen.findByRole('option', { name: '1h' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '1d' })).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.queryByText('Select a market symbol.')).not.toBeInTheDocument(),
    );
  });

  it('creates a real-data training job with symbol, timeframe, and target column', async () => {
    // A longer explicit timeout: this test drives several sequential MUI
    // Autocomplete interactions and can exceed the 5s default under the
    // CPU pressure of the full suite running in parallel, despite finishing
    // in ~2s in isolation.
    mockedTrainingApi.createTrainingJob.mockResolvedValue(jobDetail({ id: 'job-3' }));
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail({ id: 'job-3' }));
    renderPage();
    await screen.findByText('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'New Training Job' }));
    const dialog = screen.getByRole('dialog');
    await within(dialog).findByLabelText('Experiment');
    fireEvent.mouseDown(within(dialog).getByLabelText('Experiment'));
    fireEvent.click(await screen.findByRole('option', { name: 'Baseline SMA' }));
    fireEvent.mouseDown(within(dialog).getByLabelText('Model type'));
    fireEvent.click(await screen.findByRole('option', { name: 'Logistic Regression (Baseline)' }));
    const symbolField = await within(dialog).findByLabelText('Symbol');
    fireEvent.mouseDown(symbolField);
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    fireEvent.mouseDown(within(dialog).getByLabelText('Timeframe'));
    fireEvent.click(await screen.findByRole('option', { name: '1h' }));
    fireEvent.change(within(dialog).getByLabelText('Target column'), {
      target: { value: 'next_direction_1' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Create Training Job' }));

    await waitFor(() =>
      expect(mockedTrainingApi.createTrainingJob).toHaveBeenCalledWith(
        expect.objectContaining({
          model_type: 'logistic_regression',
          symbol: 'ETHUSD',
          timeframe: '1h',
          target_column: 'next_direction_1',
        }),
      ),
    );
  }, 15000);
});

describe('MLTrainingPage — job detail, run, and cancel', () => {
  it('opens the detail dialog for a job and shows its status monitor', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText('Status Monitor')).toBeInTheDocument();
    expect(screen.getByLabelText('Training pipeline progress')).toBeInTheDocument();
    expect(screen.getByText('Dataset Validation')).toBeInTheDocument();
  });

  it('opens the detail dialog automatically for a ?jobId= deep link', async () => {
    searchParams = new URLSearchParams({ jobId: 'job-1' });
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    renderPage();

    expect(await screen.findByText('Status Monitor')).toBeInTheDocument();
  });

  it('shows logs and a result summary once completed', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        status: 'completed',
        current_stage: 'update_experiment',
        result_summary: { metrics: { placeholder_loss: 0.1 } },
        logs: [
          {
            id: 'log-1',
            level: 'info',
            stage: 'execute_training',
            message: 'Completed stage: execute_training',
            logged_at: '2026-01-01T00:00:01Z',
          },
        ],
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText('Result Summary')).toBeInTheDocument();
    expect(screen.getByText(/placeholder_loss/)).toBeInTheDocument();
    expect(screen.getByText(/Completed stage: execute_training/)).toBeInTheDocument();
  });

  it('runs a pending job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    mockedTrainingApi.runTrainingJob.mockResolvedValue(jobDetail({ status: 'completed' }));
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));
    await screen.findByText('Status Monitor');

    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(mockedTrainingApi.runTrainingJob).toHaveBeenCalledWith('job-1'));
  });

  it('cancels a pending job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    mockedTrainingApi.cancelTrainingJob.mockResolvedValue(jobDetail({ status: 'cancelled' }));
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));
    await screen.findByText('Status Monitor');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await screen.findByText('Cancel Training Job');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Job' }));
    await waitFor(() => expect(mockedTrainingApi.cancelTrainingJob).toHaveBeenCalledWith('job-1'));
  });

  it('backing out of the cancel confirmation does not cancel the job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));
    await screen.findByText('Status Monitor');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await screen.findByText('Cancel Training Job');
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(screen.queryByText('Cancel Training Job')).not.toBeInTheDocument());
    expect(mockedTrainingApi.cancelTrainingJob).not.toHaveBeenCalled();
  });

  it('deletes a job from the detail dialog', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(jobDetail());
    mockedTrainingApi.deleteTrainingJob.mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));
    await screen.findByText('Status Monitor');

    fireEvent.click(screen.getByLabelText('Delete training job'));
    await screen.findByText('Delete Training Job');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(mockedTrainingApi.deleteTrainingJob).toHaveBeenCalledWith('job-1'));
  });

  it('shows the error message for a failed job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({ status: 'failed', error_message: 'missing_dataset_version' }),
    );
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByRole('alert')).toHaveTextContent('missing_dataset_version');
  });

  it('shows the structured error detail (affected feature, rows, suggested fix) for a failed job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        status: 'failed',
        error_message: "Feature column 'sma_20' has an undefined value (row 3)",
        error_detail: {
          reason: "Feature column 'sma_20' has an undefined value (row 3)",
          affected_feature: 'sma_20',
          affected_rows: [3],
          suggested_fix: 'Check the upstream feature generator for this column.',
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('sma_20');
    expect(alert).toHaveTextContent('Affected rows: 3');
    expect(alert).toHaveTextContent('Check the upstream feature generator for this column.');
  });

  it('renders a confusion matrix for a completed classification job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        model_type: 'logistic_regression',
        status: 'completed',
        current_stage: 'update_experiment',
        result_summary: {
          metrics: { accuracy: 0.9, precision: 0.85, recall: 0.8, f1: 0.82 },
          artifact_uri: 'file:///tmp/model.joblib',
          classes: ['down', 'up'],
          confusion_matrix: [
            [4, 1],
            [0, 5],
          ],
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText('Confusion Matrix')).toBeInTheDocument();
    expect(screen.getByText('Accuracy')).toBeInTheDocument();
    // The Train/Validation/Test table below also renders the validation column
    // with this same value, so more than one match is expected here.
    expect(screen.getAllByText('0.9000').length).toBeGreaterThan(0);
  });

  it('renders regression metrics for a completed regression job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        model_type: 'linear_regression',
        status: 'completed',
        current_stage: 'update_experiment',
        result_summary: {
          metrics: { mae: 1.5, mse: 3.2, rmse: 1.79, r2: 0.91 },
          artifact_uri: 'file:///tmp/model.joblib',
        },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText('MAE')).toBeInTheDocument();
    expect(screen.getByText('R²')).toBeInTheDocument();
    expect(screen.queryByText('Confusion Matrix')).not.toBeInTheDocument();
  });

  it('renders feature importance, ROC/PR curves, prediction samples, and model metadata for a completed classification job', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        model_type: 'logistic_regression',
        status: 'completed',
        current_stage: 'update_experiment',
        result_summary: {
          metrics: { accuracy: 0.9, precision: 0.85, recall: 0.8, f1: 0.82 },
          artifact_uri: 'file:///tmp/model.joblib',
          classes: ['down', 'up'],
          confusion_matrix: [
            [4, 1],
            [0, 5],
          ],
          confusion_matrix_details: [
            {
              class: 'up',
              true_positive: 5,
              false_positive: 1,
              true_negative: 4,
              false_negative: 0,
              support: 5,
            },
          ],
          train_metrics: { accuracy: 0.99 },
          test_metrics: { accuracy: 0.88 },
          overfitting: {
            flagged: false,
            gap: 0.09,
            threshold: 0.15,
            message: 'No significant gap.',
          },
          roc_pr_curves: {
            curves: {
              up: {
                roc: { fpr: [0, 1], tpr: [0, 1] },
                pr: { precision: [1, 0.5], recall: [0, 1] },
              },
            },
            auc: { up: 0.93 },
            average_precision: { up: 0.9 },
            macro_auc: 0.93,
          },
          feature_importance: [
            { feature: 'sma_20', coefficient: 0.5, abs_importance: 0.5, sign: 'positive' },
          ],
          prediction_samples: [
            {
              actual: 'up',
              predicted: 'up',
              probability: 0.9,
              confidence_level: 'high',
              correct: true,
            },
          ],
          model_metadata: {
            sklearn_version: '1.5.0',
            joblib_version: '1.4.2',
            training_duration_seconds: 0.01,
            cpu_time_seconds: 0.01,
            memory_usage_mb: 50,
            feature_count: 1,
            sample_count: 10,
          },
        },
      }),
    );
    mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({
      job_id: 'job-1',
      artifacts: [
        {
          artifact_type: 'feature_importance_csv',
          filename: 'feature_importance.csv',
          content_type: 'text/csv',
          download_url: '/api/v1/training-jobs/job-1/artifacts/feature_importance_csv',
        },
      ],
    });
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText('Confusion Matrix Details')).toBeInTheDocument();
    expect(screen.getByText('Train / Validation / Test Metrics')).toBeInTheDocument();
    expect(screen.getByText('No significant gap.')).toBeInTheDocument();
    expect(screen.getByText('ROC & Precision-Recall Curves')).toBeInTheDocument();
    expect(screen.getByText('Feature Importance')).toBeInTheDocument();
    expect(screen.getByText('sma_20')).toBeInTheDocument();
    expect(screen.getByText('Prediction Samples')).toBeInTheDocument();
    expect(screen.getByText('Model Metadata')).toBeInTheDocument();
    expect(
      await screen.findByText('Feature importance (feature_importance.csv)'),
    ).toBeInTheDocument();
  });

  it('highlights overfitting for a completed regression job with a large train/test gap', async () => {
    mockedTrainingApi.fetchTrainingJob.mockResolvedValue(
      jobDetail({
        model_type: 'linear_regression',
        status: 'completed',
        current_stage: 'update_experiment',
        result_summary: {
          metrics: { mae: 0.5, mse: 0.3, rmse: 0.55, r2: 0.98 },
          artifact_uri: 'file:///tmp/model.joblib',
          train_metrics: { mae: 0.01, mse: 0.001, rmse: 0.03, r2: 0.999 },
          test_metrics: { mae: 5.0, mse: 30.0, rmse: 5.5, r2: 0.4 },
          overfitting: {
            flagged: true,
            gap: 0.599,
            threshold: 0.15,
            message: 'Train metric exceeds the held-out metric — possible overfitting.',
          },
          feature_importance: [
            { feature: 'close', coefficient: -0.2, abs_importance: 0.2, sign: 'negative' },
          ],
        },
      }),
    );
    mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({ job_id: 'job-1', artifacts: [] });
    renderPage();
    fireEvent.click(await screen.findByText('placeholder'));

    expect(await screen.findByText(/possible overfitting/)).toBeInTheDocument();
  });
});
