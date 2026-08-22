import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrderBookEmptyState } from './order-book-empty-state';

afterEach(() => {
  cleanup();
});

function renderNotice(props: Partial<React.ComponentProps<typeof OrderBookEmptyState>> = {}) {
  return render(
    <OrderBookEmptyState
      symbol="ETHUSD"
      isUntracked={false}
      connectionState="open"
      hasBook
      isBookEmpty={false}
      onRetry={vi.fn()}
      {...props}
    />,
  );
}

describe('OrderBookEmptyState', () => {
  it('renders nothing once a non-empty book exists', () => {
    const { container } = renderNotice();
    expect(container).toBeEmptyDOMElement();
  });

  it('explains an untracked market', () => {
    renderNotice({ isUntracked: true, hasBook: false });
    expect(screen.getByText(/is not on the live feed/)).toBeInTheDocument();
  });

  it('explains a genuinely empty reconstructed book', () => {
    renderNotice({ hasBook: true, isBookEmpty: true });
    expect(screen.getByText(/order book for ETHUSD is empty/)).toBeInTheDocument();
  });

  it('says the stream is connected but the first snapshot has not arrived', () => {
    renderNotice({ hasBook: false, connectionState: 'open' });
    expect(screen.getByText(/first snapshot has not arrived/)).toBeInTheDocument();
  });

  it('reports an automatic reconnect in progress', () => {
    renderNotice({ hasBook: false, connectionState: 'reconnecting' });
    expect(screen.getByText(/Reconnecting to the ETHUSD order book/)).toBeInTheDocument();
    expect(screen.getByText(/dropped and is reconnecting automatically/)).toBeInTheDocument();
  });

  it('says the stream is not connected yet', () => {
    renderNotice({ hasBook: false, connectionState: 'closed' });
    expect(screen.getByText(/not connected yet/)).toBeInTheDocument();
  });

  it('offers a retry action', () => {
    const onRetry = vi.fn();
    renderNotice({ hasBook: false, onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('prioritizes the untracked explanation over a generic waiting message', () => {
    renderNotice({ isUntracked: true, hasBook: false, connectionState: 'closed' });
    expect(screen.getByText(/is not on the live feed/)).toBeInTheDocument();
    expect(screen.queryByText(/not connected yet/)).not.toBeInTheDocument();
  });
});
