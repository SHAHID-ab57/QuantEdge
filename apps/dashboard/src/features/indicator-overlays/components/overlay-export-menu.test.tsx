import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { OverlayChartSeries } from '../lib/overlay-series';
import { OverlayExportMenu } from './overlay-export-menu';

function series(overrides: Partial<OverlayChartSeries> = {}): OverlayChartSeries {
  return {
    id: 'a',
    label: 'SMA(20)',
    color: '#2196f3',
    data: [{ time: 1_735_689_600, value: 100 }] as never,
    ok: true,
    ...overrides,
  };
}

beforeAll(() => {
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: vi.fn(() => 'blob:mock'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('OverlayExportMenu', () => {
  it('downloads a CSV file when Export CSV is chosen', () => {
    const createObjectURL = vi.mocked(URL.createObjectURL);
    render(<OverlayExportMenu symbol="ETHUSD" timeframe="1h" overlays={[series()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Export overlays' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export CSV' }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0]![0] as Blob;
    expect(blob.type).toContain('text/csv');
  });

  it('downloads a JSON file when Export JSON is chosen', () => {
    const createObjectURL = vi.mocked(URL.createObjectURL);
    render(<OverlayExportMenu symbol="ETHUSD" timeframe="1h" overlays={[series()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Export overlays' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export JSON' }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0]![0] as Blob;
    expect(blob.type).toContain('application/json');
  });

  it('copies values to the clipboard and shows feedback', async () => {
    render(<OverlayExportMenu symbol="ETHUSD" timeframe="1h" overlays={[series()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Export overlays' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Copy Values' }));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Overlay values copied to clipboard')).toBeInTheDocument();
  });
});
