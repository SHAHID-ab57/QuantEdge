import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experimentsApi from '@/lib/api/experiments';
import type { Experiment } from '@/types/api/experiments';
import { ExperimentDetailPage } from './experiment-detail-page';

vi.mock('@/lib/api/experiments', () => ({
  fetchExperiments: vi.fn(),
  fetchExperiment: vi.fn(),
  createExperiment: vi.fn(),
  updateExperiment: vi.fn(),
  deleteExperiment: vi.fn(),
  createMetric: vi.fn(),
  deleteMetric: vi.fn(),
  createArtifact: vi.fn(),
  deleteArtifact: vi.fn(),
}));

const pushMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

const mockedApi = vi.mocked(experimentsApi);

const EXPERIMENT_ID = '11111111-1111-4111-8111-111111111111';

function experiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: EXPERIMENT_ID,
    name: 'baseline sma',
    dataset_version: 'ds-abc123',
    feature_set: [{ feature: 'sma', params: { period: '20' } }],
    target_config: [{ target: 'next_close', params: { horizon: '1' } }],
    split_config: { train: 0.7, validation: 0.15, test: 0.15 },
    model_type: 'xgboost',
    status: 'draft',
    notes: 'first attempt',
    tags: ['baseline'],
    metrics: [
      {
        id: 'm1',
        name: 'accuracy',
        value: 0.87,
        unit: 'ratio',
        recorded_at: '2026-01-01T00:00:00Z',
      },
    ],
    artifacts: [
      {
        id: 'a1',
        artifact_type: 'dataset_export',
        uri: 'ETHUSD-1h-ml-dataset.csv',
        description: null,
        created_at: '2026-01-01T00:00:00Z',
      },
    ],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExperimentDetailPage experimentId={EXPERIMENT_ID} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApi.fetchExperiment.mockResolvedValue(experiment());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ExperimentDetailPage — loading and errors', () => {
  it('shows a loading skeleton before the experiment arrives', () => {
    mockedApi.fetchExperiment.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading experiment' })).toBeInTheDocument();
  });

  it('surfaces a load error with a retry action', async () => {
    mockedApi.fetchExperiment.mockRejectedValue(new Error('not found'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('not found');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('ExperimentDetailPage — metadata', () => {
  it('shows the experiment name, status, and dataset version', async () => {
    renderPage();
    expect(await screen.findByText('baseline sma')).toBeInTheDocument();
    expect(screen.getAllByText('Draft').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ds-abc123/).length).toBeGreaterThan(0);
  });

  it('shows the feature set, target, and split configuration', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    const metadata = screen.getByLabelText('Experiment metadata');
    expect(within(metadata).getByText('sma')).toBeInTheDocument();
    expect(within(metadata).getByText('next_close')).toBeInTheDocument();
    expect(within(metadata).getByText('70% / 15% / 15%')).toBeInTheDocument();
  });

  it('changing the status select calls updateExperiment', async () => {
    mockedApi.updateExperiment.mockResolvedValue(experiment({ status: 'running' }));
    renderPage();
    await screen.findByText('baseline sma');

    const statusControl = within(screen.getByLabelText('Experiment status')).getByRole('combobox');
    fireEvent.mouseDown(statusControl);
    fireEvent.click(screen.getByRole('option', { name: 'Running' }));

    await waitFor(() =>
      expect(mockedApi.updateExperiment).toHaveBeenCalledWith(EXPERIMENT_ID, {
        status: 'running',
      }),
    );
  });
});

describe('ExperimentDetailPage — notes and tags', () => {
  it('edits and saves notes', async () => {
    mockedApi.updateExperiment.mockResolvedValue(experiment({ notes: 'updated notes' }));
    renderPage();
    await screen.findByText('baseline sma');

    fireEvent.click(screen.getByRole('button', { name: 'Edit notes' }));
    const notesInput = within(screen.getByLabelText('Edit experiment notes')).getByRole('textbox');
    fireEvent.change(notesInput, { target: { value: 'updated notes' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(mockedApi.updateExperiment).toHaveBeenCalledWith(EXPERIMENT_ID, {
        notes: 'updated notes',
      }),
    );
  });

  it('adding a tag calls updateExperiment with the full replacement tag set', async () => {
    mockedApi.updateExperiment.mockResolvedValue(experiment({ tags: ['baseline', 'sma'] }));
    renderPage();
    await screen.findByText('baseline sma');

    const tagsInput = within(screen.getByLabelText('Experiment tags')).getByRole('combobox');
    fireEvent.change(tagsInput, { target: { value: 'sma' } });
    fireEvent.keyDown(tagsInput, { key: 'Enter' });

    await waitFor(() =>
      expect(mockedApi.updateExperiment).toHaveBeenCalledWith(EXPERIMENT_ID, {
        tags: ['baseline', 'sma'],
      }),
    );
  });
});

describe('ExperimentDetailPage — metrics and artifacts', () => {
  it('shows recorded metrics', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    expect(screen.getByText('accuracy')).toBeInTheDocument();
    expect(screen.getByText('0.87')).toBeInTheDocument();
  });

  it('adds a metric', async () => {
    mockedApi.createMetric.mockResolvedValue({
      id: 'm2',
      name: 'sharpe',
      value: 1.2,
      unit: null,
      recorded_at: '2026-01-03T00:00:00Z',
    });
    renderPage();
    await screen.findByText('baseline sma');

    fireEvent.change(screen.getByLabelText('Metric name'), { target: { value: 'sharpe' } });
    fireEvent.change(screen.getByLabelText('Metric value'), { target: { value: '1.2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Metric' }));

    await waitFor(() =>
      expect(mockedApi.createMetric).toHaveBeenCalledWith(EXPERIMENT_ID, {
        name: 'sharpe',
        value: 1.2,
        unit: null,
      }),
    );
  });

  it('deletes a metric', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'Delete metric accuracy' }));

    await waitFor(() => expect(mockedApi.deleteMetric).toHaveBeenCalledWith(EXPERIMENT_ID, 'm1'));
  });

  it('shows recorded artifacts', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    expect(screen.getByText('ETHUSD-1h-ml-dataset.csv')).toBeInTheDocument();
  });

  it('adds an artifact', async () => {
    mockedApi.createArtifact.mockResolvedValue({
      id: 'a2',
      artifact_type: 'report',
      uri: 'report.pdf',
      description: null,
      created_at: '2026-01-03T00:00:00Z',
    });
    renderPage();
    await screen.findByText('baseline sma');

    fireEvent.change(screen.getByLabelText('Artifact URI'), { target: { value: 'report.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Artifact' }));

    await waitFor(() =>
      expect(mockedApi.createArtifact).toHaveBeenCalledWith(EXPERIMENT_ID, {
        artifact_type: 'dataset_export',
        uri: 'report.pdf',
        description: null,
      }),
    );
  });

  it('deletes an artifact', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(
      screen.getByRole('button', { name: 'Delete artifact ETHUSD-1h-ml-dataset.csv' }),
    );

    await waitFor(() => expect(mockedApi.deleteArtifact).toHaveBeenCalledWith(EXPERIMENT_ID, 'a1'));
  });
});

describe('ExperimentDetailPage — deleting the experiment', () => {
  it('opens a confirmation dialog before deleting', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(screen.getByText('Delete Experiment')).toBeInTheDocument();
    expect(mockedApi.deleteExperiment).not.toHaveBeenCalled();
  });

  it('deletes and navigates back to the list on confirm', async () => {
    mockedApi.deleteExperiment.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(mockedApi.deleteExperiment).toHaveBeenCalledWith(EXPERIMENT_ID));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/experiments'));
  });

  it('cancelling the dialog does not delete', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(mockedApi.deleteExperiment).not.toHaveBeenCalled();
  });
});
