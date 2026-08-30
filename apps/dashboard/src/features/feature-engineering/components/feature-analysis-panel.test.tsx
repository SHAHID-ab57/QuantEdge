import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as hooks from '../hooks/use-feature-data';
import { FeatureAnalysisPanel } from './feature-analysis-panel';

vi.mock('../hooks/use-feature-data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/use-feature-data')>();
  return {
    ...actual,
    useComputeCorrelation: vi.fn(),
    useComputeStatistics: vi.fn(),
  };
});

const mocked = vi.mocked(hooks);

afterEach(() => cleanup());

/** A loosely-typed stand-in for a `useMutation` result — cast at the call
 * site to whichever of the two mutation result types is needed, since both
 * share the same shape (`mutate`/`isPending`/`isError`/`error`/`data`) and
 * only differ in `data`'s own type. */
function mutationResult(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    data: undefined,
    ...overrides,
  };
}

function renderPanel() {
  render(
    <ThemeProvider theme={theme}>
      <FeatureAnalysisPanel symbol="ETHUSD" params={{ timeframe: '1h', features: [] }} />
    </ThemeProvider>,
  );
}

describe('FeatureAnalysisPanel', () => {
  it('renders an Analyze button before anything has been computed', () => {
    mocked.useComputeCorrelation.mockReturnValue(mutationResult() as never);
    mocked.useComputeStatistics.mockReturnValue(mutationResult() as never);
    renderPanel();
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeInTheDocument();
  });

  it('calls both mutations with the same request when Analyze is clicked', () => {
    const correlationMutate = vi.fn();
    const statisticsMutate = vi.fn();
    mocked.useComputeCorrelation.mockReturnValue(
      mutationResult({ mutate: correlationMutate }) as never,
    );
    mocked.useComputeStatistics.mockReturnValue(
      mutationResult({ mutate: statisticsMutate }) as never,
    );
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Analyze' }));
    expect(correlationMutate).toHaveBeenCalledWith({
      symbol: 'ETHUSD',
      params: { timeframe: '1h', features: [] },
    });
    expect(statisticsMutate).toHaveBeenCalledWith({
      symbol: 'ETHUSD',
      params: { timeframe: '1h', features: [] },
    });
  });

  it('renders both results once available', () => {
    mocked.useComputeCorrelation.mockReturnValue(
      mutationResult({
        data: {
          symbol: 'ETHUSD',
          timeframe: '1h',
          columns: ['a', 'b'],
          matrix: [
            [1, 0],
            [0, 1],
          ],
          row_count: 2,
        },
      }) as never,
    );
    mocked.useComputeStatistics.mockReturnValue(
      mutationResult({
        data: {
          symbol: 'ETHUSD',
          timeframe: '1h',
          columns: [
            { column: 'a', count: 2, null_count: 0, mean: 1, std: 0, minimum: 1, maximum: 1 },
          ],
          row_count: 2,
        },
      }) as never,
    );
    renderPanel();
    expect(screen.getByText('Full Dataset Statistics')).toBeInTheDocument();
    expect(screen.getByText('Correlation Matrix')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Re-analyze' })).toBeInTheDocument();
  });

  it('surfaces a correlation error', () => {
    mocked.useComputeCorrelation.mockReturnValue(
      mutationResult({ isError: true, error: new Error('boom') }) as never,
    );
    mocked.useComputeStatistics.mockReturnValue(mutationResult() as never);
    renderPanel();
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
  });
});
