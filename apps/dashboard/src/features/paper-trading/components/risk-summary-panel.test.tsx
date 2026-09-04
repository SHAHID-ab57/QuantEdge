import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { RiskSummary } from '@/types/api/paper-trading';
import { RiskSummaryPanel } from './risk-summary-panel';

const DATA: RiskSummary = {
  account_id: 'account-1',
  balance: '89984.995',
  peak_balance: '100000',
  current_exposure_pct: '11.11',
  max_exposure_pct: '50',
  exposure_headroom_pct: '38.89',
  current_drawdown_pct: '10.015',
  max_drawdown_pct: '20',
  drawdown_headroom_pct: '9.985',
  max_position_size_pct: '10',
  trading_halted: false,
};

afterEach(() => cleanup());

function renderPanel(overrides: Partial<Parameters<typeof RiskSummaryPanel>[0]> = {}) {
  const onResume = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <RiskSummaryPanel
        data={DATA}
        isLoading={false}
        onResume={onResume}
        resuming={false}
        resumeError={null}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onResume };
}

describe('RiskSummaryPanel', () => {
  it('shows a trading-active chip and both limit rows when not halted', () => {
    renderPanel();
    expect(screen.getByText('Trading active')).toBeInTheDocument();
    expect(screen.getByText('11.11% / 50.00% limit')).toBeInTheDocument();
    expect(screen.getByText('10.02% / 20.00% limit')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume Trading' })).not.toBeInTheDocument();
  });

  it('shows a halted alert with a Resume Trading action', () => {
    renderPanel({ data: { ...DATA, trading_halted: true, current_drawdown_pct: '25' } });
    expect(screen.getByRole('alert')).toHaveTextContent('Trading halted');
    expect(screen.getByRole('button', { name: 'Resume Trading' })).toBeInTheDocument();
  });

  it('confirms before calling onResume', async () => {
    const { onResume } = renderPanel({ data: { ...DATA, trading_halted: true } });

    fireEvent.click(screen.getByRole('button', { name: 'Resume Trading' }));
    expect(onResume).not.toHaveBeenCalled();

    const confirmButtons = await screen.findAllByRole('button', { name: 'Resume Trading' });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]!);

    expect(onResume).toHaveBeenCalledTimes(1);
  });

  it('surfaces a resume error', () => {
    renderPanel({
      data: { ...DATA, trading_halted: true },
      resumeError: 'Could not resume trading.',
    });
    expect(screen.getByText('Could not resume trading.')).toBeInTheDocument();
  });

  it('renders skeletons while loading', () => {
    renderPanel({ data: undefined, isLoading: true });
    expect(screen.queryByText('Trading active')).not.toBeInTheDocument();
  });
});
