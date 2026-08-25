import { ThemeProvider } from '@mui/material/styles';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { Feature } from '@/types/api/features';
import { useFavoriteFeaturesStore } from '../store/use-favorite-features-store';
import { useRecentFeaturesStore } from '../store/use-recent-features-store';
import type { FeatureSelection } from '../lib/feature-selection';
import { FeatureSelector } from './feature-selector';

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

function candleShape(): Feature {
  return {
    name: 'candle_shape',
    label: 'Candle Shape',
    description: 'Body, wicks, and direction.',
    category: 'price_action',
    parameters: [],
    outputs: ['candle_body', 'upper_wick', 'lower_wick', 'candle_direction'],
    version: '1.0.0',
    author: 'Eth AI Platform',
    complexity: 'O(n)',
    warmup_description: 'None.',
    dependencies: [],
  };
}

function renderSelector(props: Partial<React.ComponentProps<typeof FeatureSelector>> = {}) {
  const onToggle = vi.fn();
  const onParamsChange = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <FeatureSelector
        features={[ohlcv(), sma(), candleShape()]}
        selections={[]}
        onToggle={onToggle}
        onParamsChange={onParamsChange}
        {...props}
      />
    </ThemeProvider>,
  );
  return { ...utils, onToggle, onParamsChange };
}

afterEach(() => {
  cleanup();
  act(() => useRecentFeaturesStore.getState().clear());
  act(() => useFavoriteFeaturesStore.getState().clear());
  sessionStorage.clear();
  localStorage.clear();
});

describe('FeatureSelector — listing', () => {
  it('lists every generator from the catalogue', () => {
    renderSelector();
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
  });

  it('groups generators under category headings, raw data first', () => {
    renderSelector();
    expect(screen.getByText('Raw Market Data')).toBeInTheDocument();
    expect(screen.getByText('Trend')).toBeInTheDocument();
  });

  it('shows a skeleton while the catalogue loads', () => {
    renderSelector({ loading: true });
    expect(screen.getByRole('status', { name: 'Loading feature catalogue' })).toBeInTheDocument();
    expect(screen.queryByText('OHLCV')).not.toBeInTheDocument();
  });

  it('reports an empty catalogue rather than rendering nothing', () => {
    renderSelector({ features: [] });
    expect(screen.getByText('No feature generators are registered.')).toBeInTheDocument();
  });

  it('exposes each generator’s documentation via an info tooltip', () => {
    renderSelector();
    expect(screen.getByRole('button', { name: 'About Simple Moving Average' })).toBeInTheDocument();
  });
});

describe('FeatureSelector — search', () => {
  it('filters by label', () => {
    renderSelector();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'moving' },
    });
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.queryByText('OHLCV')).not.toBeInTheDocument();
  });

  it('filters by description', () => {
    renderSelector();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'raw candle' },
    });
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
    expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
  });

  it('shows a no-matches message for a query matching nothing', () => {
    renderSelector();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByText('No features match “nonexistent”.')).toBeInTheDocument();
  });
});

describe('FeatureSelector — category filter', () => {
  it('lists every present category as a filter option', () => {
    renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Category' }));
    expect(screen.getByRole('option', { name: 'trend' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'raw' })).toBeInTheDocument();
  });

  it('shows only features in the selected category', () => {
    renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Category' }));
    fireEvent.click(screen.getByRole('option', { name: 'trend' }));
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.queryByText('OHLCV')).not.toBeInTheDocument();
  });

  it('shows every feature again when reset to all categories', () => {
    renderSelector();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Category' }));
    fireEvent.click(screen.getByRole('option', { name: 'trend' }));
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Category' }));
    fireEvent.click(screen.getByRole('option', { name: 'All categories' }));
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
  });
});

describe('FeatureSelector — keyboard navigation', () => {
  it('moves focus to the next visible checkbox on ArrowDown', () => {
    renderSelector();
    const ohlcvCheckbox = screen.getByRole('checkbox', { name: 'Include OHLCV' });
    ohlcvCheckbox.focus();
    fireEvent.keyDown(ohlcvCheckbox, { key: 'ArrowDown' });
    // Candle Shape sorts before SMA alphabetically within "price_action"/"trend"
    // groups, but OHLCV (raw) is always first — the next row after it is
    // whichever comes next in rendered order.
    expect(document.activeElement).not.toBe(ohlcvCheckbox);
    expect(document.activeElement).toHaveAttribute('aria-label');
  });

  it('moves focus to the previous visible checkbox on ArrowUp', () => {
    renderSelector();
    const smaCheckbox = screen.getByRole('checkbox', { name: 'Include Simple Moving Average' });
    smaCheckbox.focus();
    fireEvent.keyDown(smaCheckbox, { key: 'ArrowUp' });
    expect(document.activeElement).not.toBe(smaCheckbox);
  });

  it('wraps from the last row back to the first on ArrowDown', () => {
    renderSelector({ features: [ohlcv(), sma()] });
    const smaCheckbox = screen.getByRole('checkbox', { name: 'Include Simple Moving Average' });
    smaCheckbox.focus();
    fireEvent.keyDown(smaCheckbox, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
  });

  it('only navigates among currently-filtered rows', () => {
    renderSelector();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'moving' },
    });
    const smaCheckbox = screen.getByRole('checkbox', { name: 'Include Simple Moving Average' });
    smaCheckbox.focus();
    fireEvent.keyDown(smaCheckbox, { key: 'ArrowDown' });
    // Only one row matches the filter, so it wraps to itself.
    expect(document.activeElement).toBe(smaCheckbox);
  });
});

describe('FeatureSelector — recently used', () => {
  it('shows no recently-used section before anything has been toggled', () => {
    renderSelector();
    expect(screen.queryByText('Recently used:')).not.toBeInTheDocument();
  });

  it('lists a feature as recently used after it is toggled on', () => {
    renderSelector();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    expect(screen.getByText('Recently used:')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Toggle Simple Moving Average (recently used)' }),
    ).toBeInTheDocument();
  });

  it('toggles a feature via its recently-used chip', () => {
    const selections: FeatureSelection[] = [];
    const { onToggle, rerender } = renderSelector({ selections });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    onToggle.mockClear();

    // Deselect via the store update a real page would apply, then use the
    // chip to re-add it.
    rerender(
      <ThemeProvider theme={theme}>
        <FeatureSelector
          features={[ohlcv(), sma(), candleShape()]}
          selections={[]}
          onToggle={onToggle}
          onParamsChange={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Toggle Simple Moving Average (recently used)' }),
    );
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0]![0].name).toBe('sma');
  });

  it('moves a re-toggled feature back to the front of the recent list', () => {
    renderSelector();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include OHLCV' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    const chips = screen.getAllByRole('button', { name: /recently used/ });
    expect(chips[0]).toHaveAccessibleName(/Simple Moving Average/);
  });
});

describe('FeatureSelector — selection', () => {
  it('reports a toggle when a generator is ticked', () => {
    const { onToggle } = renderSelector();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0]![0].name).toBe('sma');
  });

  it('renders a selected generator as checked', () => {
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    renderSelector({ selections });
    expect(screen.getByRole('checkbox', { name: 'Include Simple Moving Average' })).toBeChecked();
  });

  it('summarizes a selected generator’s parameters', () => {
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    renderSelector({ selections });
    expect(screen.getByText('period=20')).toBeInTheDocument();
  });

  it('offers a details action even for a parameterless generator, once selected', () => {
    const selections: FeatureSelection[] = [{ feature: 'ohlcv', params: {} }];
    renderSelector({ selections });
    expect(screen.getByRole('button', { name: 'Show details for OHLCV' })).toBeInTheDocument();
  });

  it('offers no details action before the generator is selected', () => {
    renderSelector();
    expect(
      screen.queryByRole('button', { name: 'Show details for Simple Moving Average' }),
    ).not.toBeInTheDocument();
  });
});

describe('FeatureSelector — feature details', () => {
  it('reveals description, warmup, and dependencies when expanded', () => {
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    renderSelector({ selections });
    fireEvent.click(screen.getByRole('button', { name: 'Show details for Simple Moving Average' }));
    // Appears twice: once as the row's truncated secondary line, once in
    // full in the expanded Feature Details panel.
    expect(screen.getAllByText('The unweighted mean of the last N values.').length).toBe(2);
    expect(screen.getByText(/Warmup: Equal to the period parameter\./)).toBeInTheDocument();
    expect(screen.getByText(/Dependencies: None/)).toBeInTheDocument();
  });

  it('lists declared dependencies when present', () => {
    const dependent: Feature = { ...sma(), name: 'derived', dependencies: ['sma'] };
    const selections: FeatureSelection[] = [{ feature: 'derived', params: {} }];
    renderSelector({ features: [dependent], selections });
    fireEvent.click(screen.getByRole('button', { name: 'Show details for Simple Moving Average' }));
    expect(screen.getByText(/Dependencies: sma/)).toBeInTheDocument();
  });
});

describe('FeatureSelector — parameters', () => {
  it('reveals a parameter form built from the published specs', () => {
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    renderSelector({ selections });
    fireEvent.click(screen.getByRole('button', { name: 'Show details for Simple Moving Average' }));
    expect(screen.getByLabelText('Period')).toBeInTheDocument();
  });

  it('commits a valid parameter change', () => {
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    const { onParamsChange } = renderSelector({ selections });
    fireEvent.click(screen.getByRole('button', { name: 'Show details for Simple Moving Average' }));
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '50' } });
    expect(onParamsChange).toHaveBeenCalledWith('sma', { period: '50' });
  });

  it('does not commit an out-of-range value, and says why', () => {
    // Sending a value we already know is invalid would spend a round trip
    // to be told so, and would replace a working dataset with an error.
    const selections: FeatureSelection[] = [{ feature: 'sma', params: { period: '20' } }];
    const { onParamsChange } = renderSelector({ selections });
    fireEvent.click(screen.getByRole('button', { name: 'Show details for Simple Moving Average' }));
    fireEvent.change(screen.getByLabelText('Period'), { target: { value: '0' } });
    expect(onParamsChange).not.toHaveBeenCalled();
    expect(screen.getByText(/Must be at least 1/)).toBeInTheDocument();
  });
});

describe('FeatureSelector — metadata display', () => {
  it('shows each generators version, category, and column count', () => {
    renderSelector();
    expect(screen.getByText(/v1\.0\.0 · trend · 1 column/)).toBeInTheDocument();
    expect(screen.getByText(/v1\.0\.0 · raw · 5 columns/)).toBeInTheDocument();
  });
});

describe('FeatureSelector — favorites', () => {
  it('shows no favorites row before anything has been starred', () => {
    renderSelector();
    expect(screen.queryByText('Favorites:')).not.toBeInTheDocument();
  });

  it('stars a feature and lists it under Favorites', () => {
    renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average to favorites' }));
    expect(screen.getByText('Favorites:')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Toggle Simple Moving Average (favorite)' }),
    ).toBeInTheDocument();
  });

  it('unstars a feature via its own toggle button', () => {
    renderSelector();
    const star = screen.getByRole('button', { name: 'Add Simple Moving Average to favorites' });
    fireEvent.click(star);
    fireEvent.click(
      screen.getByRole('button', { name: 'Remove Simple Moving Average from favorites' }),
    );
    expect(screen.queryByText('Favorites:')).not.toBeInTheDocument();
  });

  it('marks the star button as pressed once favorited', () => {
    renderSelector();
    const star = screen.getByRole('button', { name: 'Add Simple Moving Average to favorites' });
    expect(star).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(star);
    expect(
      screen.getByRole('button', { name: 'Remove Simple Moving Average from favorites' }),
    ).toHaveAttribute('aria-pressed', 'true');
  });

  it('toggles selection via a favorite chip', () => {
    const { onToggle } = renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average to favorites' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Toggle Simple Moving Average (favorite)' }),
    );
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0]![0].name).toBe('sma');
  });

  it('persists favorites across a remount (localStorage, not sessionStorage)', () => {
    const { unmount } = renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Add Simple Moving Average to favorites' }));
    unmount();
    renderSelector();
    expect(screen.getByText('Favorites:')).toBeInTheDocument();
  });
});

describe('FeatureSelector — expand/collapse categories', () => {
  it('starts with every category expanded', () => {
    renderSelector();
    expect(screen.getByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse Trend' })).toBeInTheDocument();
  });

  it('collapsing a category hides its rows', async () => {
    renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Trend' }));
    // MUI's Collapse unmounts its content only once its exit transition
    // completes, which is asynchronous even in a test environment.
    await waitFor(() => {
      expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
    });
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
  });

  it('re-expands a collapsed category', async () => {
    renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Trend' }));
    await waitFor(() => {
      expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand Trend' }));
    expect(await screen.findByText('Simple Moving Average')).toBeInTheDocument();
  });

  it('Collapse All hides every category, Expand All restores them', async () => {
    renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse All' }));
    await waitFor(() => {
      expect(screen.queryByText('Simple Moving Average')).not.toBeInTheDocument();
      expect(screen.queryByText('OHLCV')).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Expand All' }));
    expect(await screen.findByText('Simple Moving Average')).toBeInTheDocument();
    expect(screen.getByText('OHLCV')).toBeInTheDocument();
  });

  it('keyboard navigation skips rows in a collapsed category', () => {
    renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Trend' }));
    const ohlcvCheckbox = screen.getByRole('checkbox', { name: 'Include OHLCV' });
    ohlcvCheckbox.focus();
    fireEvent.keyDown(ohlcvCheckbox, { key: 'ArrowDown' });
    // SMA (Trend) is collapsed, so the only other visible row is Candle Shape.
    expect(document.activeElement).toBe(
      screen.getByRole('checkbox', { name: 'Include Candle Shape' }),
    );
  });
});

describe('FeatureSelector — select all / clear all', () => {
  it('selects every currently-filtered feature', () => {
    const { onToggle } = renderSelector();
    fireEvent.click(screen.getByRole('button', { name: 'Select All' }));
    expect(onToggle).toHaveBeenCalledTimes(3);
  });

  it('only selects features matching an active search', () => {
    const { onToggle } = renderSelector();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'moving' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Select All' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0]![0].name).toBe('sma');
  });

  it('clears every selection, even ones hidden by an active filter', () => {
    const selections: FeatureSelection[] = [
      { feature: 'ohlcv', params: {} },
      { feature: 'sma', params: { period: '20' } },
    ];
    const { onToggle } = renderSelector({ selections });
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'moving' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Clear All' }));
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('disables Select All when nothing is visible, and Clear All when nothing is selected', () => {
    renderSelector();
    expect(screen.getByRole('button', { name: 'Clear All' })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search features' }), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByRole('button', { name: 'Select All' })).toBeDisabled();
  });
});
