import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { TapeExportButton } from './tape-export-button';

function trade(price: string, size: string, side = 'buy'): LiveTradeData {
  return { price, size, side, event_time: '2026-01-01T00:00:00Z' };
}

let clicked: { href: string; download: string } | null = null;

beforeEach(() => {
  clicked = null;
  // jsdom implements neither object URLs nor real navigation, so both are
  // stubbed — the assertion below is that the component *asked* for a
  // download with the right filename, not that a file landed on disk.
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:fake'),
    revokeObjectURL: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked = { href: this.href, download: this.download };
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('TapeExportButton', () => {
  it('is disabled when there is nothing visible to export', () => {
    render(<TapeExportButton trades={[]} symbol="ETHUSD" sideFilter="all" minSize={0} />);
    expect(
      screen.getByRole('button', { name: 'Export visible trade tape rows as CSV' }),
    ).toBeDisabled();
  });

  it('triggers a download named for the symbol when clicked', () => {
    render(
      <TapeExportButton
        trades={[trade('100', '2')]}
        symbol="ETHUSD"
        sideFilter="all"
        minSize={0}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Export visible trade tape rows as CSV' }));
    expect(clicked).not.toBeNull();
    expect(clicked!.download).toContain('ETHUSD-trade-tape-');
    expect(clicked!.download.endsWith('.csv')).toBe(true);
  });

  it('has an accessible name that says the export covers the visible rows', () => {
    render(
      <TapeExportButton
        trades={[trade('100', '2')]}
        symbol="ETHUSD"
        sideFilter="buy"
        minSize={5}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Export visible trade tape rows as CSV' }),
    ).toBeInTheDocument();
  });
});
