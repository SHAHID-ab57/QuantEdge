import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { Indicator } from '@/types/api/indicators';
import { useOverlayStore } from '../store/use-overlay-store';
import { IndicatorPanel } from './indicator-panel';

function sma(): Indicator {
  return {
    name: 'sma',
    label: 'Simple Moving Average',
    description: 'The unweighted mean of the last N values.',
    category: 'trend',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'Equal to the period parameter.',
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
    outputs: [{ name: 'sma', label: 'SMA', description: '' }],
  };
}

function rsi(): Indicator {
  return {
    name: 'rsi',
    label: 'Relative Strength Index',
    description: 'A 0-100 momentum oscillator.',
    category: 'momentum',
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'One more than the period parameter.',
    parameters: [],
    outputs: [{ name: 'rsi', label: 'RSI', description: '' }],
  };
}

function renderPanel(indicators: Indicator[] = [sma(), rsi()], loading = false) {
  return render(
    <ThemeProvider theme={theme}>
      <IndicatorPanel indicators={indicators} loading={loading} />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  act(() => useOverlayStore.getState().clearOverlays());
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe('IndicatorPanel — listing', () => {
  it('lists every available indicator', () => {
    renderPanel();
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.getByText('Relative Strength Index')).toBeInTheDocument();
  });

  it('shows a loading skeleton instead of the list while loading', () => {
    renderPanel([sma()], true);
    expect(screen.getByRole('status', { name: 'Loading indicators' })).toBeInTheDocument();
    expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
  });

  it('says the overlay list is empty before anything is added', () => {
    renderPanel();
    expect(
      screen.getByText('Add an indicator above to overlay it on the chart.'),
    ).toBeInTheDocument();
  });
});

describe('IndicatorPanel — search', () => {
  it('filters by label', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search indicators' }), {
      target: { value: 'relative' },
    });
    expect(screen.getByText('Relative Strength Index')).toBeInTheDocument();
    expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
  });

  it('filters by category', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search indicators' }), {
      target: { value: 'momentum' },
    });
    expect(screen.getByText('Relative Strength Index')).toBeInTheDocument();
    expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
  });

  it('shows a no-matches message for a query matching nothing', () => {
    renderPanel();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search indicators' }), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByText('No indicators match “nonexistent”.')).toBeInTheDocument();
  });
});

describe('IndicatorPanel — add', () => {
  it('adds an overlay to the store when Add is clicked', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    expect(useOverlayStore.getState().overlays).toHaveLength(1);
    expect(useOverlayStore.getState().overlays[0]!.indicator).toBe('sma');
  });

  it('shows an "Added" chip once an indicator has an overlay', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    expect(screen.getByText('Added')).toBeInTheDocument();
  });

  it('adds the overlay when the row itself is clicked, not just the icon button', () => {
    renderPanel();
    fireEvent.click(screen.getByText('Simple Moving Average'));
    expect(useOverlayStore.getState().overlays).toHaveLength(1);
  });

  it('allows adding the same indicator more than once', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    expect(useOverlayStore.getState().overlays).toHaveLength(2);
  });
});

describe('IndicatorPanel — manage overlays', () => {
  it('shows the overlay with its resolved parameters', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    expect(screen.getByText('period=20')).toBeInTheDocument();
  });

  it('toggles an overlay off and on', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    const toggle = screen.getByRole('switch', { name: 'Disable Simple Moving Average' });
    fireEvent.click(toggle);
    expect(useOverlayStore.getState().overlays[0]!.enabled).toBe(false);
  });

  it('removes an overlay', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove Simple Moving Average' }));
    expect(useOverlayStore.getState().overlays).toHaveLength(0);
  });

  it('expands a parameter form when Configure is clicked', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Configure Simple Moving Average' }));
    expect(screen.getByLabelText('Period')).toBeInTheDocument();
  });

  it('updates the overlay’s params in the store when a valid value is entered', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Configure Simple Moving Average' }));
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '50' } });
    expect(useOverlayStore.getState().overlays[0]!.params).toEqual({ period: '50' });
  });

  it('does not commit an out-of-range value to the store', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average' }));
    fireEvent.click(screen.getByRole('button', { name: 'Configure Simple Moving Average' }));
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '0' } });
    expect(useOverlayStore.getState().overlays[0]!.params).toEqual({ period: '20' });
    expect(screen.getByText(/Must be at least 1/)).toBeInTheDocument();
  });
});
