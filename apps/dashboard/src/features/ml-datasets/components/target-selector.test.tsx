import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { TargetDTO } from '@/types/api/ml-datasets';
import type { TargetSelection } from '../lib/target-selection';
import { TargetSelector } from './target-selector';

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

function renderSelector(selections: TargetSelection[] = []) {
  const onToggle = vi.fn();
  const onParamsChange = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <TargetSelector
        targets={[nextClose(), nextDirection()]}
        selections={selections}
        onToggle={onToggle}
        onParamsChange={onParamsChange}
      />
    </ThemeProvider>,
  );
  return { ...utils, onToggle, onParamsChange };
}

afterEach(() => cleanup());

describe('TargetSelector — searchable dropdown', () => {
  it('opens to a searchable combobox rather than a fixed checkbox list', async () => {
    renderSelector();
    const input = screen.getByRole('combobox', { name: 'Search prediction targets' });
    fireEvent.mouseDown(input);
    expect(await screen.findByRole('option', { name: /Next Closing Price/ })).toBeInTheDocument();
    expect(
      await screen.findByRole('option', { name: /Next Candle Direction/ }),
    ).toBeInTheDocument();
  });

  it('offers a search placeholder rather than a static "pick one" prompt', () => {
    renderSelector();
    expect(screen.getByPlaceholderText('Search targets…')).toBeInTheDocument();
  });

  it('shows each option’s problem type, description, output, and horizon compatibility', async () => {
    renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Search prediction targets' }));
    const option = await screen.findByRole('option', { name: /Next Closing Price/ });
    expect(option).toHaveTextContent('Regression');
    expect(option).toHaveTextContent('Predicts the next candle closing price.');
    expect(option).toHaveTextContent('next_close_{horizon}');
    expect(option).toHaveTextContent('Horizon 1–500 candles ahead');
  });

  it('selecting an option calls onToggle for that target', async () => {
    const { onToggle } = renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Search prediction targets' }));
    fireEvent.click(await screen.findByRole('option', { name: /Next Closing Price/ }));
    expect(onToggle).toHaveBeenCalledWith(nextClose());
  });

  it('removing a tag calls onToggle to deselect that target', () => {
    const { onToggle } = renderSelector([{ target: 'next_close', params: { horizon: '1' } }]);
    fireEvent.click(screen.getByRole('button', { name: /Remove Next Closing Price/ }));
    expect(onToggle).toHaveBeenCalledWith(nextClose());
  });
});

describe('TargetSelector — selected target configuration', () => {
  it('renders a card per selected target with its output columns', () => {
    renderSelector([{ target: 'next_close', params: { horizon: '1' } }]);
    expect(screen.getByText('next_close_{horizon}')).toBeInTheDocument();
  });

  it('offers a horizon preset dropdown seeded from the current value', () => {
    renderSelector([{ target: 'next_close', params: { horizon: '5' } }]);
    expect(screen.getByLabelText('Horizon')).toHaveTextContent('5 candles');
  });

  it('commits a preset horizon change', () => {
    const { onParamsChange } = renderSelector([{ target: 'next_close', params: { horizon: '1' } }]);
    fireEvent.mouseDown(screen.getByLabelText('Horizon'));
    fireEvent.click(screen.getByRole('option', { name: '5 candles' }));
    expect(onParamsChange).toHaveBeenCalledWith('next_close', { horizon: '5' });
  });

  it('reveals a custom numeric field when Custom… is chosen', () => {
    renderSelector([{ target: 'next_close', params: { horizon: '1' } }]);
    fireEvent.mouseDown(screen.getByLabelText('Horizon'));
    fireEvent.click(screen.getByRole('option', { name: 'Custom…' }));
    expect(screen.getByLabelText('Custom prediction horizon')).toBeInTheDocument();
  });

  it('removing a target via its card’s remove button calls onToggle', () => {
    const { onToggle } = renderSelector([{ target: 'next_close', params: { horizon: '1' } }]);
    fireEvent.click(screen.getByRole('button', { name: 'Remove Next Closing Price' }));
    expect(onToggle).toHaveBeenCalledWith(nextClose());
  });
});

describe('TargetSelector — empty/loading states', () => {
  it('shows a loading skeleton', () => {
    render(
      <ThemeProvider theme={theme}>
        <TargetSelector
          targets={[]}
          loading
          selections={[]}
          onToggle={vi.fn()}
          onParamsChange={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole('status', { name: 'Loading target catalogue' })).toBeInTheDocument();
  });

  it('reports when no targets are registered', () => {
    render(
      <ThemeProvider theme={theme}>
        <TargetSelector targets={[]} selections={[]} onToggle={vi.fn()} onParamsChange={vi.fn()} />
      </ThemeProvider>,
    );
    expect(screen.getByText('No target generators are registered.')).toBeInTheDocument();
  });
});
