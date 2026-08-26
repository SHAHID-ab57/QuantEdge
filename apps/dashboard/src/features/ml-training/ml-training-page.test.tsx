import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experimentsApi from '@/lib/api/experiments';
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
}));

const mockedExperimentsApi = vi.mocked(experimentsApi);
const mockedTrainingApi = vi.mocked(trainingApi);

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
        hyperparameter_hints: ['epochs', 'learning_rate'],
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
  mockedTrainingApi.fetchTrainingJobs.mockResolvedValue(listResponse());
  mockedTrainingApi.fetchModelAdapters.mockResolvedValue(modelAdapters());
  mockedExperimentsApi.fetchExperiments.mockResolvedValue(experimentListResponse());
  mockedExperimentsApi.fetchExperiment.mockResolvedValue(experimentDetail());
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
});
