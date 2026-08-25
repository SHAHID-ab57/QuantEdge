import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureSelection } from '@/features/feature-engineering/lib/feature-selection';
import type { Feature } from '@/types/api/features';
import { useRecentColumnsStore } from '../store/use-recent-columns-store';
import { RequiredColumnsSelector } from './required-columns-selector';

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
  };
}

function sma(): Feature {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'Rolling mean.',
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
    warmup_description: 'Equal to the period.',
  };
}

function renderSelector(props: Partial<React.ComponentProps<typeof RequiredColumnsSelector>> = {}) {
  const onChange = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <RequiredColumnsSelector
        features={[ohlcv(), sma()]}
        selections={[]}
        value={[]}
        onChange={onChange}
        {...props}
      />
    </ThemeProvider>,
  );
  return { ...utils, onChange };
}

afterEach(() => {
  cleanup();
  act(() => useRecentColumnsStore.getState().clear());
  sessionStorage.clear();
});

describe('RequiredColumnsSelector — display', () => {
  it('shows a tooltip explaining the field', () => {
    renderSelector();
    expect(screen.getByRole('button', { name: 'About Required columns' })).toBeInTheDocument();
  });

  it('reports the total selected count', () => {
    renderSelector({ value: ['close', 'sma_20'] });
    expect(screen.getByText('(2 selected)')).toBeInTheDocument();
  });

  it('renders each selected value as a removable chip', () => {
    renderSelector({ value: ['close'] });
    expect(screen.getByText('close')).toBeInTheDocument();
  });
});

describe('RequiredColumnsSelector — search and multi-select', () => {
  it('offers every resolved column, grouped by category, when opened', () => {
    renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Required columns' }));
    expect(screen.getByRole('option', { name: /close/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /sma_20/ })).toBeInTheDocument();
    expect(screen.getByText('Raw Market Data')).toBeInTheDocument();
    expect(screen.getByText('Technical Indicators')).toBeInTheDocument();
  });

  it('filters options by search text', () => {
    renderSelector();
    const input = screen.getByRole('combobox', { name: 'Required columns' });
    fireEvent.change(input, { target: { value: 'sma' } });
    expect(screen.getByRole('option', { name: /sma_20/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /^close/ })).not.toBeInTheDocument();
  });

  it('selecting an option adds it to the value', () => {
    const { onChange } = renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Required columns' }));
    fireEvent.click(screen.getByRole('option', { name: /close/ }));
    expect(onChange).toHaveBeenCalledWith(['close']);
  });

  it('resolves a selected features own parameters, not the default, into its option', () => {
    renderSelector({
      selections: [{ feature: 'sma', params: { period: '50' } } as FeatureSelection],
    });
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Required columns' }));
    expect(screen.getByRole('option', { name: /sma_50/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /sma_20/ })).not.toBeInTheDocument();
  });

  it('accepts a free-typed column name not in the option list', () => {
    const { onChange } = renderSelector();
    const input = screen.getByRole('combobox', { name: 'Required columns' });
    fireEvent.change(input, { target: { value: 'made_up_column' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(['made_up_column']);
  });
});

describe('RequiredColumnsSelector — select all / clear all', () => {
  it('selects every resolved column', () => {
    const { onChange } = renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Select All' }));
    const [selected] = onChange.mock.calls[0] as [string[]];
    expect(selected.sort()).toEqual(['close', 'high', 'low', 'open', 'sma_20', 'volume']);
  });

  it('clears every selected column', () => {
    const { onChange } = renderSelector({ value: ['close', 'sma_20'] });
    fireEvent.click(screen.getByRole('button', { name: 'Clear All' }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('disables Clear All when nothing is selected', () => {
    renderSelector();
    expect(screen.getByRole('button', { name: 'Clear All' })).toBeDisabled();
  });
});

describe('RequiredColumnsSelector — recently used', () => {
  it('shows no recently-used row before anything has been added', () => {
    renderSelector();
    expect(screen.queryByText('Recently used:')).not.toBeInTheDocument();
  });

  it('offers a recently-used column not currently selected', () => {
    act(() => useRecentColumnsStore.getState().recordUsed('close'));
    renderSelector();
    expect(screen.getByText('Recently used:')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add close (recently used column)' }),
    ).toBeInTheDocument();
  });

  it('adding a recently-used chip commits it to the value', () => {
    act(() => useRecentColumnsStore.getState().recordUsed('close'));
    const { onChange } = renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Add close (recently used column)' }));
    expect(onChange).toHaveBeenCalledWith(['close']);
  });

  it('does not offer a column that is already selected', () => {
    act(() => useRecentColumnsStore.getState().recordUsed('close'));
    renderSelector({ value: ['close'] });
    expect(
      screen.queryByRole('button', { name: 'Add close (recently used column)' }),
    ).not.toBeInTheDocument();
  });
});
