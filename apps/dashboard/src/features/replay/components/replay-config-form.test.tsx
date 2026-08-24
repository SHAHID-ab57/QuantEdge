import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as marketApi from '@/lib/api/market';
import type { Market } from '@/types/api/market';
import { ReplayConfigForm } from './replay-config-form';

vi.mock('@/lib/api/market', () => ({
  fetchMarkets: vi.fn(),
  fetchTimeframes: vi.fn(),
}));

const mockedMarket = vi.mocked(marketApi);

const markets: Market[] = [
  {
    id: '1',
    symbol: 'ETHUSD',
    exchange: 'Delta Exchange',
    exchange_id: 'e1',
    base_asset: 'ETH',
    quote_asset: 'USD',
    market_type: 'perpetual',
    is_active: true,
    delta_product_id: 1,
    delta_contract_type: 'perpetual_futures',
    tick_size: '0.01',
    funding_method: 'mark_price',
    funding_interval_seconds: 28800,
    listing_date: null,
  },
];

function renderForm(onSubmitted = vi.fn(), disabled = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ReplayConfigForm onSubmitted={onSubmitted} disabled={disabled} />
    </QueryClientProvider>,
  );
  return { onSubmitted };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ReplayConfigForm', () => {
  it('requires a market, timeframe, start, and end before submitting', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
    const { onSubmitted } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));

    await waitFor(() => {
      expect(screen.getByText('Select a market')).toBeInTheDocument();
    });
    expect(onSubmitted).not.toHaveBeenCalled();
  });

  it('rejects an end time that is before the start time', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
    mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1m'] });
    const { onSubmitted } = renderForm();

    const combobox = screen.getByRole('combobox', { name: 'Select a market to replay' });
    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Timeframe' })).not.toHaveAttribute(
        'aria-disabled',
        'true',
      ),
    );
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }));
    fireEvent.click(await screen.findByRole('option', { name: '1m' }));
    fireEvent.change(screen.getByLabelText('Replay start'), {
      target: { value: '2026-01-02T00:00' },
    });
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T00:00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));

    await waitFor(() =>
      expect(screen.getByText('End must be after the start')).toBeInTheDocument(),
    );
    expect(onSubmitted).not.toHaveBeenCalled();
  });

  it('rejects an end time in the future', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
    mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1m'] });
    const { onSubmitted } = renderForm();

    const combobox = screen.getByRole('combobox', { name: 'Select a market to replay' });
    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Timeframe' })).not.toHaveAttribute(
        'aria-disabled',
        'true',
      ),
    );
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }));
    fireEvent.click(await screen.findByRole('option', { name: '1m' }));
    fireEvent.change(screen.getByLabelText('Replay start'), {
      target: { value: '2026-01-01T00:00' },
    });
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2099-01-01T00:00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));

    await waitFor(() =>
      expect(screen.getByText('End cannot be in the future')).toBeInTheDocument(),
    );
    expect(onSubmitted).not.toHaveBeenCalled();
  });

  it('submits valid values', async () => {
    mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
    mockedMarket.fetchTimeframes.mockResolvedValue({ symbol: 'ETHUSD', timeframes: ['1m'] });
    const { onSubmitted } = renderForm();

    const combobox = screen.getByRole('combobox', { name: 'Select a market to replay' });
    fireEvent.mouseDown(combobox);
    fireEvent.click(await screen.findByRole('option', { name: 'ETHUSD' }));
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Timeframe' })).not.toHaveAttribute(
        'aria-disabled',
        'true',
      ),
    );
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Timeframe' }));
    fireEvent.click(await screen.findByRole('option', { name: '1m' }));
    fireEvent.change(screen.getByLabelText('Replay start'), {
      target: { value: '2026-01-01T00:00' },
    });
    fireEvent.change(screen.getByLabelText('Replay end'), {
      target: { value: '2026-01-01T06:00' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Load Session' }));
      // react-hook-form's Zod resolver resolves asynchronously even for a
      // fully synchronous schema; flushing one microtask turn here is what
      // lets `onSubmitted` actually fire before this `act()` block exits.
      await Promise.resolve();
    });

    // react-hook-form's handleSubmit invokes onValid as (values, event) —
    // the second argument (the native submit event) is asserted loosely.
    expect(onSubmitted).toHaveBeenCalledWith(
      expect.objectContaining({ market: 'ETHUSD', timeframe: '1m' }),
      expect.anything(),
    );
  });

  it('disables the submit button while a session is already loading', () => {
    mockedMarket.fetchMarkets.mockResolvedValue({ markets, total: 1 });
    renderForm(vi.fn(), true);
    expect(screen.getByRole('button', { name: 'Load Session' })).toBeDisabled();
  });
});
