import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { theme } from '@/theme/theme';
import type { PaperStrategyDecisionListResponse } from '@/types/api/paper-trading';
import { StrategyDecisionLogTable } from './strategy-decision-log-table';

const DATA: PaperStrategyDecisionListResponse = {
  decisions: [
    {
      id: 'decision-1',
      account_id: 'account-1',
      training_job_id: 'job-1',
      symbol: 'ETHUSD',
      action: 'opened',
      reason: "Confidence 90.00% >= 65% threshold; signal 'up' while flat — opened 5 ETHUSD.",
      predicted_value: 'up',
      confidence: 0.9,
      confidence_threshold_pct: '65',
      prediction_id: 'prediction-1',
      order_id: 'order-1',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
};

afterEach(() => cleanup());

function renderTable(overrides: Partial<Parameters<typeof StrategyDecisionLogTable>[0]> = {}) {
  render(
    <ThemeProvider theme={theme}>
      <StrategyDecisionLogTable
        data={DATA}
        isLoading={false}
        page={1}
        limit={10}
        onPageChange={() => {}}
        {...overrides}
      />
    </ThemeProvider>,
  );
}

describe('StrategyDecisionLogTable', () => {
  it('renders a decision with its symbol, signal, confidence, and reason', () => {
    renderTable();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('up')).toBeInTheDocument();
    expect(screen.getByText('90.0%')).toBeInTheDocument();
    expect(screen.getByText(/opened 5 ETHUSD/)).toBeInTheDocument();
  });

  it('shows a filled Opened chip', () => {
    renderTable();
    expect(screen.getByText('Opened')).toBeInTheDocument();
  });

  it('shows a filled Closed chip for a close decision', () => {
    renderTable({
      data: {
        ...DATA,
        decisions: [{ ...DATA.decisions[0]!, action: 'closed', order_id: 'order-2' }],
      },
    });
    expect(screen.getByText('Closed')).toBeInTheDocument();
  });

  it('shows a distinct outlined No Action chip for a no-op cycle, with no order', () => {
    renderTable({
      data: {
        ...DATA,
        decisions: [
          {
            ...DATA.decisions[0]!,
            action: 'no_action',
            order_id: null,
            reason: 'Confidence 50.00% is below the 65% threshold.',
          },
        ],
      },
    });
    expect(screen.getByText('No Action')).toBeInTheDocument();
    expect(screen.queryByText('Opened')).not.toBeInTheDocument();
    expect(screen.getByText(/below the 65% threshold/)).toBeInTheDocument();
  });

  it('reports an empty log', () => {
    renderTable({ data: { decisions: [], total: 0, limit: 10, offset: 0 } });
    expect(
      screen.getByText('No strategy cycles logged yet — enable the strategy above to start.'),
    ).toBeInTheDocument();
  });
});
