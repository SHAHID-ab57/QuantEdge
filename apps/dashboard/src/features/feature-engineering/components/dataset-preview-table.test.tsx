import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { FeatureDataset } from '@/types/api/features';
import { DatasetPreviewTable } from './dataset-preview-table';

function dataset(overrides: Partial<FeatureDataset> = {}): FeatureDataset {
  return {
    dataset_id: '11111111-1111-4111-8111-111111111111',
    symbol: 'ETHUSD',
    timeframe: '1h',
    columns: [
      { name: 'close', label: 'Close', description: 'Closing price.', dtype: 'float' },
      {
        name: 'candle_direction',
        label: 'Candle Direction',
        description: 'Sign of the body.',
        dtype: 'categorical',
      },
    ],
    timestamps: ['2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z'],
    rows: [
      [100.5, 'up'],
      [101.25, 'down'],
    ],
    features: [
      {
        feature: 'ohlcv',
        label: 'OHLCV',
        version: '1.0.0',
        parameters: {},
        columns: ['close'],
        warmup: 0,
        execution_time_ms: 0.1,
      },
    ],
    meta: {
      row_count: 2,
      total_rows: 2,
      candles_analyzed: 2,
      rows_dropped: 0,
      warmup_candles: 0,
      truncated: false,
      database_time_ms: 1.2,
      pipeline_version: '1.0.0',
      generated_at: '2026-01-01T02:00:00Z',
    },
    quality: {
      total_rows: 2,
      rows_returned: 2,
      rows_removed: 0,
      null_counts: {},
      duplicate_timestamps: 0,
      missing_candles: 0,
      feature_failures: [],
      generation_time_ms: 0.5,
    },
    ...overrides,
  };
}

function renderTable(props: Partial<React.ComponentProps<typeof DatasetPreviewTable>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <DatasetPreviewTable dataset={dataset()} {...props} />
    </ThemeProvider>,
  );
}

afterEach(() => cleanup());

describe('DatasetPreviewTable', () => {
  it('renders a column header per dataset column, plus the timestamp', () => {
    renderTable();
    expect(screen.getByText('Timestamp')).toBeInTheDocument();
    expect(screen.getByText('close')).toBeInTheDocument();
    expect(screen.getByText('candle_direction')).toBeInTheDocument();
  });

  it('renders one row per timestamp', () => {
    renderTable();
    expect(screen.getByText('2026-01-01T00:00:00Z')).toBeInTheDocument();
    expect(screen.getByText('2026-01-01T01:00:00Z')).toBeInTheDocument();
  });

  it('renders cell values, formatting floats for display', () => {
    renderTable();
    expect(screen.getByText('100.5')).toBeInTheDocument();
    expect(screen.getByText('up')).toBeInTheDocument();
  });

  it('exposes each column’s dtype via its info tooltip', () => {
    // A researcher must know whether a column is continuous or categorical
    // before deciding how to model it; the name alone rarely says.
    renderTable();
    expect(screen.getByRole('button', { name: 'About candle_direction' })).toBeInTheDocument();
  });

  it('renders a null cell as an em dash rather than an empty gap', () => {
    renderTable({
      dataset: dataset({
        rows: [
          [null, 'up'],
          [101.25, 'down'],
        ],
      }),
    });
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('says the dataset is a preview when it was truncated', () => {
    renderTable({
      dataset: dataset({
        meta: { ...dataset().meta, truncated: true, row_count: 2, total_rows: 5000 },
      }),
    });
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByText(/Showing 2 of 5,000 rows/)).toBeInTheDocument();
  });

  it('says exports contain everything, so a preview is never mistaken for the whole set', () => {
    renderTable({
      dataset: dataset({ meta: { ...dataset().meta, truncated: true, total_rows: 5000 } }),
    });
    expect(screen.getByText(/Exports always contain the full dataset/)).toBeInTheDocument();
  });

  it('shows no preview notice when everything fits', () => {
    renderTable();
    expect(screen.queryByText('Preview')).not.toBeInTheDocument();
  });

  it('reports an empty dataset with an actionable reason', () => {
    renderTable({ dataset: dataset({ rows: [], timestamps: [] }) });
    expect(screen.getByRole('status')).toHaveTextContent(/dropped as warmup/);
  });

  it('reports a dataset with no columns', () => {
    renderTable({ dataset: dataset({ columns: [], rows: [], timestamps: [] }) });
    expect(screen.getByRole('status')).toHaveTextContent(/No columns were produced/);
  });

  it('caps rendered rows when asked', () => {
    renderTable({ maxRows: 1 });
    expect(screen.getByText('2026-01-01T00:00:00Z')).toBeInTheDocument();
    expect(screen.queryByText('2026-01-01T01:00:00Z')).not.toBeInTheDocument();
  });
});

describe('DatasetPreviewTable — ML dataset extensions (target columns and split)', () => {
  it('marks a target column with a "target" badge in its header', () => {
    renderTable({ targetColumns: ['candle_direction'] });
    expect(screen.getByText('target')).toBeInTheDocument();
  });

  it('does not badge a feature column', () => {
    renderTable({ targetColumns: ['candle_direction'] });
    expect(screen.getAllByText('target')).toHaveLength(1);
  });

  it('renders no Split column when splitLabels is omitted', () => {
    renderTable();
    expect(screen.queryByText('Split')).not.toBeInTheDocument();
  });

  it('renders a Split column with a per-row label when splitLabels is provided', () => {
    renderTable({ splitLabels: ['train', 'validation'] });
    expect(screen.getByText('Split')).toBeInTheDocument();
    expect(screen.getByText('train')).toBeInTheDocument();
    expect(screen.getByText('validation')).toBeInTheDocument();
  });

  it('caps split labels along with rows when maxRows is set', () => {
    renderTable({ splitLabels: ['train', 'validation'], maxRows: 1 });
    expect(screen.getByText('train')).toBeInTheDocument();
    expect(screen.queryByText('validation')).not.toBeInTheDocument();
  });
});

describe('DatasetPreviewTable — column search and visibility', () => {
  it('renders a column search box', () => {
    renderTable();
    expect(screen.getByPlaceholderText('Search columns…')).toBeInTheDocument();
  });

  it('hides columns whose name does not match the search text', () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText('Search columns…'), {
      target: { value: 'close' },
    });
    expect(screen.getByText('close')).toBeInTheDocument();
    expect(screen.queryByText('candle_direction')).not.toBeInTheDocument();
  });

  it('reports when no column matches the search text', () => {
    renderTable();
    fireEvent.change(screen.getByPlaceholderText('Search columns…'), {
      target: { value: 'nonexistent' },
    });
    expect(screen.getByRole('status')).toHaveTextContent(/No columns match/);
  });

  it('offers a column-visibility menu that can hide a column', () => {
    renderTable();
    fireEvent.click(screen.getByRole('button', { name: 'Toggle column visibility' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Toggle close visibility' }));
    const table = document.querySelector('table') as HTMLElement;
    expect(within(table).queryByText('close')).not.toBeInTheDocument();
    expect(within(table).getByText('candle_direction')).toBeInTheDocument();
    expect(screen.getByText('1 column hidden')).toBeInTheDocument();
  });

  it('re-shows a hidden column when toggled again', () => {
    renderTable();
    fireEvent.click(screen.getByRole('button', { name: 'Toggle column visibility' }));
    const item = screen.getByRole('menuitem', { name: 'Toggle close visibility' });
    fireEvent.click(item);
    fireEvent.click(item);
    const table = document.querySelector('table') as HTMLElement;
    expect(within(table).getByText('close')).toBeInTheDocument();
    expect(screen.queryByText(/column hidden/)).not.toBeInTheDocument();
  });

  it('resets hidden columns when the dataset changes shape', () => {
    const { rerender } = renderTable();
    fireEvent.click(screen.getByRole('button', { name: 'Toggle column visibility' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Toggle close visibility' }));
    expect(
      within(document.querySelector('table') as HTMLElement).queryByText('close'),
    ).not.toBeInTheDocument();

    rerender(
      <ThemeProvider theme={theme}>
        <DatasetPreviewTable
          dataset={dataset({
            columns: [{ name: 'sma_20', label: 'SMA', description: '', dtype: 'float' }],
            rows: [[1], [2]],
          })}
        />
      </ThemeProvider>,
    );
    expect(
      within(document.querySelector('table') as HTMLElement).getByText('sma_20'),
    ).toBeInTheDocument();
  });
});

describe('DatasetPreviewTable — sticky first column', () => {
  it('keeps the Timestamp header sticky at the left edge', () => {
    renderTable();
    const header = screen.getByText('Timestamp').closest('th');
    expect(header).toHaveStyle({ position: 'sticky', left: '0px' });
  });
});

describe('DatasetPreviewTable — column statistics popover', () => {
  it('offers a statistics popup for a numeric column', () => {
    renderTable();
    expect(screen.getByRole('button', { name: 'Show statistics for close' })).toBeInTheDocument();
  });

  it('does not offer a statistics popup for a categorical column', () => {
    renderTable();
    expect(
      screen.queryByRole('button', { name: 'Show statistics for candle_direction' }),
    ).not.toBeInTheDocument();
  });

  it('shows the computed min/max when the popup is opened', () => {
    renderTable();
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(screen.getByText('Min')).toBeInTheDocument();
    // The values also appear in the table body, hence both instead of one.
    expect(screen.getAllByText('100.5')).toHaveLength(2);
    expect(screen.getAllByText('101.25')).toHaveLength(2);
  });

  it('notes the statistics are preview-scoped when maxRows caps the table', () => {
    renderTable({ maxRows: 1 });
    fireEvent.click(screen.getByRole('button', { name: 'Show statistics for close' }));
    expect(screen.getByText(/rendered preview rows only/)).toBeInTheDocument();
  });
});

function largeDataset(rowCount: number): FeatureDataset {
  const base = Date.parse('2020-01-01T00:00:00Z');
  const hour = 3_600_000;
  return dataset({
    timestamps: Array.from({ length: rowCount }, (_, i) => new Date(base + i * hour).toISOString()),
    rows: Array.from({ length: rowCount }, (_, i) => [100 + i, i % 2 === 0 ? 'up' : 'down']),
    meta: { ...dataset().meta, total_rows: rowCount, row_count: rowCount },
  });
}

describe('DatasetPreviewTable — virtualization (large datasets)', () => {
  it('does not mount every row for a 100,000-row dataset', () => {
    renderTable({ dataset: largeDataset(100_000) });
    // Far fewer <tr> elements than rows exist — the whole point of
    // virtualizing: the DOM cost must not scale with dataset size.
    const rows = document.querySelectorAll('tbody tr');
    expect(rows.length).toBeLessThan(200);
  });

  it('renders the first rows on initial mount', () => {
    renderTable({ dataset: largeDataset(100_000) });
    expect(screen.getByText('100')).toBeInTheDocument(); // row 0's close value
  });

  it('renders a different window of rows after scrolling', () => {
    renderTable({ dataset: largeDataset(100_000) });
    const scrollContainer = document.querySelector('.MuiTableContainer-root') as HTMLElement;
    expect(scrollContainer).not.toBeNull();

    // Row 0's value must not still be the only thing rendered after
    // scrolling deep into the dataset.
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 50_000, writable: true });
    fireEvent.scroll(scrollContainer, { target: { scrollTop: 50_000 } });

    expect(screen.queryByText('100')).not.toBeInTheDocument();
  });

  it('keeps the total scrollable height proportional to the full row count via spacers', () => {
    // The two spacer rows' combined height plus the rendered rows' height
    // must account for the whole dataset, or the scrollbar itself would
    // misreport how much content exists.
    renderTable({ dataset: largeDataset(100_000) });
    const rows = Array.from(document.querySelectorAll('tbody tr'));
    const totalHeight = rows.reduce((sum, row) => {
      const height = (row as HTMLElement).style.height;
      return sum + (height ? Number.parseFloat(height) : 33);
    }, 0);
    // 100,000 rows at 33px each — allow generous rounding slack.
    expect(totalHeight).toBeGreaterThan(100_000 * 33 - 1000);
    expect(totalHeight).toBeLessThan(100_000 * 33 + 1000);
  });
});
