import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { FeatureImportancePanel } from './feature-importance-panel';

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    writable: true,
    value: vi.fn(),
  });
});

afterEach(() => cleanup());

const ROWS = [
  { feature: 'sma_20', coefficient: 0.5, abs_importance: 0.5, sign: 'positive' as const },
  { feature: 'rsi_14', coefficient: -0.9, abs_importance: 0.9, sign: 'negative' as const },
  { feature: 'volume', coefficient: 0.0, abs_importance: 0.0, sign: 'neutral' as const },
];

describe('FeatureImportancePanel', () => {
  it('renders a row per feature, sorted by importance by default', () => {
    render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={ROWS} />
      </ThemeProvider>,
    );
    const cells = screen.getAllByRole('cell');
    expect(cells[0]).toHaveTextContent('rsi_14');
  });

  it('re-sorts when a column header is clicked', () => {
    render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={ROWS} />
      </ThemeProvider>,
    );
    // First click on a new column sorts descending; alphabetically that's "volume".
    fireEvent.click(screen.getByText('Feature'));
    expect(screen.getAllByRole('cell')[0]).toHaveTextContent('volume');
    // A second click on the same column toggles to ascending.
    fireEvent.click(screen.getByText('Feature'));
    expect(screen.getAllByRole('cell')[0]).toHaveTextContent('rsi_14');
  });

  it('renders nothing for a malformed or empty rows value', () => {
    const { container: withNull } = render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={null} />
      </ThemeProvider>,
    );
    expect(withNull).toBeEmptyDOMElement();
    cleanup();
    const { container: withEmpty } = render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={[]} />
      </ThemeProvider>,
    );
    expect(withEmpty).toBeEmptyDOMElement();
  });

  it('downloads a CSV when the download button is pressed', async () => {
    const onDownloadCsv = vi.fn().mockResolvedValue(new Blob(['a,b'], { type: 'text/csv' }));
    render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={ROWS} onDownloadCsv={onDownloadCsv} />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    await waitFor(() => expect(onDownloadCsv).toHaveBeenCalled());
  });

  it('omits the download button when no download handler is given', () => {
    render(
      <ThemeProvider theme={theme}>
        <FeatureImportancePanel rows={ROWS} />
      </ThemeProvider>,
    );
    expect(screen.queryByRole('button', { name: 'Download CSV' })).not.toBeInTheDocument();
  });
});
