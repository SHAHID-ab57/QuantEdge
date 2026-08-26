import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experimentsApi from '@/lib/api/experiments';
import type { Experiment, ExperimentListResponse } from '@/types/api/experiments';
import { ExperimentsPage } from './experiments-page';

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

function summary(overrides: Partial<Experiment> = {}) {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    name: 'baseline sma',
    dataset_version: 'ds-abc',
    model_type: 'xgboost',
    status: 'draft' as const,
    tags: ['baseline'],
    metric_count: 2,
    artifact_count: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

function listResponse(overrides: Partial<ExperimentListResponse> = {}): ExperimentListResponse {
  return {
    experiments: [summary()],
    total: 1,
    limit: 20,
    offset: 0,
    statuses: ['draft', 'running', 'completed', 'failed', 'archived'],
    artifact_types: ['dataset_export', 'model_checkpoint', 'report', 'plot', 'other'],
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExperimentsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApi.fetchExperiments.mockResolvedValue(listResponse());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ExperimentsPage — listing', () => {
  it('lists experiments returned by the backend', async () => {
    renderPage();
    expect(await screen.findByText('baseline sma')).toBeInTheDocument();
  });

  it('shows a loading skeleton before the first page arrives', () => {
    mockedApi.fetchExperiments.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0);
  });

  it('surfaces a load error with a retry action', async () => {
    mockedApi.fetchExperiments.mockRejectedValue(new Error('backend down'));
    renderPage();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('backend down');
  });

  it('reports an empty result', async () => {
    mockedApi.fetchExperiments.mockResolvedValue(listResponse({ experiments: [], total: 0 }));
    renderPage();
    expect(await screen.findByText('No experiments match this search/filter.')).toBeInTheDocument();
  });
});

describe('ExperimentsPage — search, filter, and sort', () => {
  it('sends the search text as the q parameter', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.change(screen.getByLabelText('Search experiments'), {
      target: { value: 'lstm' },
    });

    await waitFor(() =>
      expect(mockedApi.fetchExperiments).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'lstm' }),
      ),
    );
  });

  it('sends the selected status as the status parameter', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.mouseDown(screen.getByLabelText('Status'));
    fireEvent.click(screen.getByRole('option', { name: 'Running' }));

    await waitFor(() =>
      expect(mockedApi.fetchExperiments).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'running' }),
      ),
    );
  });

  it('toggles sort direction when the same column header is clicked twice', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'Name' }));

    await waitFor(() =>
      expect(mockedApi.fetchExperiments).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'name', dir: 'asc' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Name' }));
    await waitFor(() =>
      expect(mockedApi.fetchExperiments).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'name', dir: 'desc' }),
      ),
    );
  });
});

describe('ExperimentsPage — creating an experiment', () => {
  it('opens the create dialog', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'New Experiment' }));
    expect(screen.getByText('Register a New Experiment')).toBeInTheDocument();
  });

  it('creates an experiment and navigates to its detail page', async () => {
    mockedApi.createExperiment.mockResolvedValue({
      id: '22222222-2222-4222-8222-222222222222',
      name: 'new experiment',
      dataset_version: null,
      feature_set: null,
      target_config: null,
      split_config: null,
      model_type: null,
      status: 'draft',
      notes: null,
      tags: [],
      metrics: [],
      artifacts: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    });
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'New Experiment' }));
    fireEvent.change(screen.getByLabelText('Experiment name'), {
      target: { value: 'new experiment' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create Experiment' }));

    await waitFor(() => expect(mockedApi.createExperiment).toHaveBeenCalled());
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith('/experiments/22222222-2222-4222-8222-222222222222'),
    );
  });

  it('cannot submit the create form without a name', async () => {
    renderPage();
    await screen.findByText('baseline sma');
    fireEvent.click(screen.getByRole('button', { name: 'New Experiment' }));
    expect(screen.getByRole('button', { name: 'Create Experiment' })).toBeDisabled();
  });
});
