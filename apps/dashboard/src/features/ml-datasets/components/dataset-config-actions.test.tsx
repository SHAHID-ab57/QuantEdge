import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { DatasetConfig } from '../lib/dataset-config';
import { DatasetConfigActions } from './dataset-config-actions';

function config(): DatasetConfig {
  return {
    market: 'ETHUSD',
    timeframe: '1h',
    range: 'all',
    start: '',
    end: '',
    limit: 500,
    features: [{ feature: 'ohlcv', params: {} }],
    targets: [{ target: 'next_close', params: { horizon: '1' } }],
    split: { train: 0.7, validation: 0.15, test: 0.15 },
  };
}

function renderActions() {
  const onImport = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <DatasetConfigActions config={config()} onImport={onImport} />
    </ThemeProvider>,
  );
  return { ...utils, onImport };
}

beforeAll(() => {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DatasetConfigActions — copy', () => {
  it('copies the serialized configuration as JSON to the clipboard', async () => {
    renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Copy Configuration' }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1));
    const text = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock
      .calls[0]![0] as string;
    expect(JSON.parse(text)).toEqual(config());
  });

  it('shows a brief confirmation after copying', async () => {
    renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Copy Configuration' }));
    expect(await screen.findByRole('button', { name: 'Copied!' })).toBeInTheDocument();
  });

  it('does not throw when clipboard access is unavailable', async () => {
    (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('denied'),
    );
    renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Copy Configuration' }));
    // No assertion beyond "did not throw" — a rejected clipboard write must
    // degrade silently, matching `validation-issue-list.tsx`'s Copy Issue.
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
  });
});

describe('DatasetConfigActions — import', () => {
  it('opens an import dialog with a paste box', () => {
    renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    expect(screen.getByText('Import Dataset Configuration')).toBeInTheDocument();
    expect(screen.getByLabelText('Paste dataset configuration JSON')).toBeInTheDocument();
  });

  it('applies a valid pasted configuration', async () => {
    const { onImport } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    fireEvent.change(screen.getByLabelText('Paste dataset configuration JSON'), {
      target: { value: JSON.stringify(config()) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(onImport).toHaveBeenCalledWith(config());
    await waitFor(() =>
      expect(screen.queryByText('Import Dataset Configuration')).not.toBeInTheDocument(),
    );
  });

  it('shows an inline error for invalid JSON and does not call onImport', () => {
    const { onImport } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    fireEvent.change(screen.getByLabelText('Paste dataset configuration JSON'), {
      target: { value: '{not json' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }));

    expect(screen.getByRole('alert')).toHaveTextContent('That is not valid JSON.');
    expect(onImport).not.toHaveBeenCalled();
  });

  it('disables Apply until something has been pasted', () => {
    renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled();
  });

  it('closes without importing when Cancel is pressed', async () => {
    const { onImport } = renderActions();
    fireEvent.click(screen.getByRole('button', { name: 'Import Configuration' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(screen.queryByText('Import Dataset Configuration')).not.toBeInTheDocument(),
    );
    expect(onImport).not.toHaveBeenCalled();
  });
});
