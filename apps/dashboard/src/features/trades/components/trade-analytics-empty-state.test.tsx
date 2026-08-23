import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TradeAnalyticsEmptyState } from './trade-analytics-empty-state';

afterEach(() => {
  cleanup();
});

function renderNotice(props: Partial<React.ComponentProps<typeof TradeAnalyticsEmptyState>> = {}) {
  return render(
    <TradeAnalyticsEmptyState
      symbol="ETHUSD"
      isUntracked={false}
      connectionState="open"
      hasAnyTrade={false}
      onRetry={vi.fn()}
      {...props}
    />,
  );
}

describe('TradeAnalyticsEmptyState', () => {
  it('renders nothing once at least one trade has been seen', () => {
    const { container } = renderNotice({ hasAnyTrade: true });
    expect(container).toBeEmptyDOMElement();
  });

  it('explains an untracked market', () => {
    renderNotice({ isUntracked: true });
    expect(screen.getByText(/is not on the live feed/)).toBeInTheDocument();
  });

  it('says the stream is connected but no trade has printed yet', () => {
    renderNotice({ connectionState: 'open' });
    expect(screen.getByText(/Waiting for the first ETHUSD trade/)).toBeInTheDocument();
    expect(screen.getByText(/no trade has printed yet/)).toBeInTheDocument();
  });

  it('reports an automatic reconnect in progress', () => {
    renderNotice({ connectionState: 'reconnecting' });
    expect(screen.getByText(/Reconnecting to the ETHUSD trade stream/)).toBeInTheDocument();
  });

  it('says the stream is not connected yet', () => {
    renderNotice({ connectionState: 'closed' });
    expect(screen.getByText(/not connected yet/)).toBeInTheDocument();
  });

  it('prioritizes the untracked explanation over a generic waiting message', () => {
    renderNotice({ isUntracked: true, connectionState: 'closed' });
    expect(screen.getByText(/is not on the live feed/)).toBeInTheDocument();
    expect(screen.queryByText(/not connected yet/)).not.toBeInTheDocument();
  });

  it('offers a retry action', () => {
    const onRetry = vi.fn();
    renderNotice({ onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
