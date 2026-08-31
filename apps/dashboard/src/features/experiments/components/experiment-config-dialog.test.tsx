import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as experimentsApi from '@/lib/api/experiments';
import * as featuresApi from '@/lib/api/features';
import * as mlDatasetsApi from '@/lib/api/ml-datasets';
import type { Experiment } from '@/types/api/experiments';
import type { Feature, FeatureCatalog } from '@/types/api/features';
import type {
  MLDatasetBuildDetailResponse,
  MLDatasetResponse,
  TargetCatalogResponse,
  TargetDTO,
} from '@/types/api/ml-datasets';
import { ExperimentConfigDialog } from './experiment-config-dialog';

vi.mock('@/lib/api/experiments', () => ({
  updateExperiment: vi.fn(),
}));

vi.mock('@/lib/api/features', () => ({
  fetchFeatures: vi.fn(),
}));

vi.mock('@/lib/api/ml-datasets', () => ({
  fetchTargets: vi.fn(),
  fetchMLDatasetBuild: vi.fn(),
}));

const mockedExperimentsApi = vi.mocked(experimentsApi);
const mockedFeaturesApi = vi.mocked(featuresApi);
const mockedMlDatasetsApi = vi.mocked(mlDatasetsApi);

function sma(): Feature {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'The unweighted mean of the last N values.',
    category: 'trend',
    parameters: [
      {
        name: 'period',
        type: 'int',
        label: 'Period',
        description: 'Window size.',
        default: 20,
        required: false,
        minimum: 1,
        maximum: 1000,
        choices: [],
      },
    ],
    outputs: ['sma_{period}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
    dependencies: [],
  };
}

function ohlcv(): Feature {
  return {
    name: 'ohlcv',
    label: 'OHLCV',
    description: 'Raw candle fields.',
    category: 'raw',
    parameters: [],
    outputs: ['open', 'high', 'low', 'close', 'volume'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'None.',
    dependencies: [],
  };
}

function featureCatalog(): FeatureCatalog {
  return { features: [sma(), ohlcv()], total: 2, categories: ['trend', 'raw'] };
}

function nextClose(): TargetDTO {
  return {
    name: 'next_close',
    label: 'Next Closing Price',
    description: 'Predicts the next candle closing price.',
    category: 'price',
    parameters: [
      {
        name: 'horizon',
        type: 'int',
        label: 'Horizon',
        description: 'Candles ahead.',
        default: 1,
        required: false,
        minimum: 1,
        maximum: 500,
        choices: [],
      },
    ],
    outputs: ['next_close_{horizon}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    value_type: 'float',
    default_horizon: 1,
    is_deterministic: true,
  };
}

function nextDirection(): TargetDTO {
  return {
    name: 'next_direction',
    label: 'Next Candle Direction',
    description: 'Predicts whether the next candle closes Up or Down.',
    category: 'direction',
    parameters: [
      {
        name: 'horizon',
        type: 'int',
        label: 'Horizon',
        description: 'Candles ahead.',
        default: 1,
        required: false,
        minimum: 1,
        maximum: 500,
        choices: [],
      },
    ],
    outputs: ['next_direction_{horizon}'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    value_type: 'categorical',
    default_horizon: 1,
    is_deterministic: true,
  };
}

function targetCatalog(): TargetCatalogResponse {
  return { targets: [nextClose(), nextDirection()], total: 2, categories: ['price', 'direction'] };
}

function experiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: 'exp-1',
    name: 'baseline sma',
    dataset_version: 'ds-abc',
    feature_set: [{ feature: 'sma', params: { period: '20' } }],
    target_config: [{ target: 'next_close', params: { horizon: '1' } }],
    split_config: { train: 0.6, validation: 0.2, test: 0.2 },
    model_type: null,
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

function mlDatasetResponse(overrides: Partial<MLDatasetResponse> = {}): MLDatasetResponse {
  return {
    ml_dataset_id: 'ml-9',
    dataset_id: 'ds-9',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [],
    feature_columns: [],
    target_columns: [],
    timestamps: [],
    rows: [],
    split: [],
    features: [],
    targets: [],
    target_failures: [],
    split_ratios: { train: 0.7, validation: 0.15, test: 0.15 },
    split_bounds: { train_rows: 0, validation_rows: 0, test_rows: 0 },
    quality: {
      total_rows: 0,
      rows_returned: 0,
      rows_removed: 0,
      null_counts: {},
      duplicate_timestamps: 0,
      missing_candles: 0,
      feature_failures: [],
      generation_time_ms: 0,
    },
    validation: {
      dataset_id: 'ds-9',
      symbol: 'ETHUSD',
      timeframe: '1h',
      engine_version: '1.0.0',
      validated_at: '2026-01-01T00:00:00Z',
      passed: true,
      rules_run: [],
      summary: { total_checks: 0, errors: 0, warnings: 0, info: 0 },
      categories: {},
      issues: [],
      rows: 0,
      columns: 0,
      duration_ms: 0,
    },
    meta: {
      row_count: 0,
      total_rows: 0,
      candles_analyzed: 0,
      rows_dropped_warmup: 0,
      rows_dropped_horizon: 0,
      warmup_candles: 0,
      max_horizon: 0,
      truncated: false,
      database_time_ms: 0,
      pipeline_version: '1.0.0',
      target_pipeline_version: '1.0.0',
      builder_version: '1.0.0',
      generated_at: '2026-01-01T00:00:00Z',
      created_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  };
}

function renderDialog(experimentValue: Experiment, onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <ExperimentConfigDialog open experiment={experimentValue} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { ...utils, onClose };
}

beforeEach(() => {
  mockedFeaturesApi.fetchFeatures.mockResolvedValue(featureCatalog());
  mockedMlDatasetsApi.fetchTargets.mockResolvedValue(targetCatalog());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ExperimentConfigDialog — round-trip on open', () => {
  it("pre-populates the editor from the experiment's existing config", async () => {
    renderDialog(experiment());

    expect(
      await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' }),
    ).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Include OHLCV' })).not.toBeChecked();
    // Renders twice — once as the Autocomplete's selected tag, once as the
    // configuration card below it — so this asserts presence, not count.
    expect(screen.getAllByText('Next Closing Price').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Train ratio')).toHaveValue(0.6);
    expect(screen.getByLabelText('Validation ratio')).toHaveValue(0.2);
    expect(screen.getByLabelText('Test ratio')).toHaveValue(0.2);
  });

  it('shows nothing selected for an experiment with no recorded config', async () => {
    renderDialog(experiment({ feature_set: null, target_config: null, split_config: null }));

    expect(
      await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' }),
    ).not.toBeChecked();
    expect(screen.queryByText('Next Closing Price')).not.toBeInTheDocument();
    // Falls back to the same 70/15/15 default the ML Dataset Builder's own form seeds.
    expect(screen.getByLabelText('Train ratio')).toHaveValue(0.7);
  });
});

describe('ExperimentConfigDialog — saving', () => {
  it('produces the exact PATCH body shape on save', async () => {
    mockedExperimentsApi.updateExperiment.mockResolvedValue(experiment());
    renderDialog(experiment());
    await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' });

    fireEvent.click(screen.getByRole('button', { name: 'Save Configuration' }));

    await waitFor(() =>
      expect(mockedExperimentsApi.updateExperiment).toHaveBeenCalledWith('exp-1', {
        feature_set: [{ feature: 'sma', params: { period: '20' } }],
        target_config: [{ target: 'next_close', params: { horizon: '1' } }],
        split_config: { train: 0.6, validation: 0.2, test: 0.2 },
      }),
    );
  });

  it('closes the dialog once the save succeeds', async () => {
    mockedExperimentsApi.updateExperiment.mockResolvedValue(experiment());
    const onClose = vi.fn();
    renderDialog(experiment(), onClose);
    await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' });

    fireEvent.click(screen.getByRole('button', { name: 'Save Configuration' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('blocks saving and lists a recorded feature no longer in the catalogue', async () => {
    renderDialog(experiment({ feature_set: [{ feature: 'stale_feature', params: {} }] }));

    expect(await screen.findByText('stale_feature')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Configuration' })).toBeDisabled();

    // MUI's Chip delete affordance is a decorative, `aria-hidden` SVG icon
    // (no accessible role of its own), so it's targeted by its test-only
    // `data-testid` rather than `getByRole` — the same way MUI's own tests
    // exercise a Chip's delete icon. Scoped to the warning alert itself,
    // since the already-selected "next_close" target tag also renders one.
    fireEvent.click(within(screen.getByRole('alert')).getByTestId('CancelIcon'));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save Configuration' })).not.toBeDisabled(),
    );
  });
});

describe('ExperimentConfigDialog — import from Dataset History', () => {
  it('pre-fills features, targets, and split from a real dataset build payload', async () => {
    const detail: MLDatasetBuildDetailResponse = {
      id: 'build-1',
      created_at: '2026-01-05T00:00:00Z',
      dataset: mlDatasetResponse({
        features: [
          {
            feature: 'ohlcv',
            label: 'OHLCV',
            version: '1.0.0',
            parameters: {},
            columns: ['open', 'high', 'low', 'close', 'volume'],
            warmup: 0,
            execution_time_ms: 1,
          },
        ],
        targets: [
          {
            target: 'next_direction',
            label: 'Next Candle Direction',
            version: '1.0.0',
            parameters: { horizon: 5 },
            columns: ['next_direction_5'],
            horizon: 5,
            execution_time_ms: 1,
          },
        ],
        split_ratios: { train: 0.5, validation: 0.25, test: 0.25 },
      }),
    };
    mockedMlDatasetsApi.fetchMLDatasetBuild.mockResolvedValue(detail);

    renderDialog(experiment());
    await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' });

    fireEvent.change(screen.getByLabelText('Dataset build ID'), {
      target: { value: 'build-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() =>
      expect(mockedMlDatasetsApi.fetchMLDatasetBuild).toHaveBeenCalledWith('build-1'),
    );

    await waitFor(() =>
      expect(
        screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }),
      ).not.toBeChecked(),
    );
    expect(screen.getByRole('checkbox', { name: 'Include OHLCV' })).toBeChecked();
    expect(screen.getAllByText('Next Candle Direction').length).toBeGreaterThan(0);
    expect(screen.queryByText('Next Closing Price')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Train ratio')).toHaveValue(0.5);
    expect(screen.getByLabelText('Validation ratio')).toHaveValue(0.25);
    expect(screen.getByLabelText('Test ratio')).toHaveValue(0.25);
  });

  it('shows an inline error when the build id does not resolve', async () => {
    mockedMlDatasetsApi.fetchMLDatasetBuild.mockRejectedValue(new Error('dataset build not found'));
    renderDialog(experiment());
    await screen.findByRole('checkbox', { name: 'Include Simple Moving Average' });

    fireEvent.change(screen.getByLabelText('Dataset build ID'), {
      target: { value: 'missing-build' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Import' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('dataset build not found');
  });
});
