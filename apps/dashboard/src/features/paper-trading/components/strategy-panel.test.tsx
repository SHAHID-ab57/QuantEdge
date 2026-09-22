import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { PaperAccount } from '@/types/api/paper-trading';
import type { TrainingJobSummary } from '@/types/api/training';
import { StrategyPanel } from './strategy-panel';

const ACCOUNT: PaperAccount = {
  id: 'account-1',
  name: 'My Account',
  starting_balance: '100000',
  balance: '100000',
  realized_pnl: '0',
  max_position_size_pct: '10',
  max_exposure_pct: '50',
  max_drawdown_pct: '20',
  max_leverage: '5',
  peak_balance: '100000',
  trading_halted: false,
  strategy_enabled: false,
  strategy_training_job_id: null,
  strategy_confidence_threshold_pct: '65',
  strategy_default_stop_loss_pct: '5',
  strategy_leverage: '2',
  strategy_paused_reason: null,
  strategy_paused_at: null,
  created_at: '2026-01-01T00:00:00Z',
};

const COMPLETED_JOB: TrainingJobSummary = {
  id: 'job-1',
  experiment_id: 'experiment-1',
  dataset_version: 'ds-1',
  model_type: 'logistic_regression',
  status: 'completed',
  current_stage: null,
  log_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

afterEach(() => cleanup());

function renderPanel(overrides: Partial<Parameters<typeof StrategyPanel>[0]> = {}) {
  const onSave = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <StrategyPanel
        account={ACCOUNT}
        isLoading={false}
        completedJobs={[COMPLETED_JOB]}
        submitting={false}
        submitError={null}
        onSave={onSave}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onSave };
}

describe('StrategyPanel', () => {
  it('states plainly that this is paper trading only', () => {
    renderPanel();
    expect(screen.getByText(/Paper trading only/)).toBeInTheDocument();
  });

  it('defaults to the account’s own strategy_enabled value (off)', () => {
    renderPanel();
    expect(screen.getByText('Strategy disabled')).toBeInTheDocument();
  });

  it('requires a training job before enabling can be saved', () => {
    renderPanel();
    fireEvent.click(screen.getByLabelText('Enable automated strategy'));
    expect(screen.getByText('Strategy enabled')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(
      screen.getByText('Required while enabled — a completed job trained on real market data'),
    ).toBeInTheDocument();
  });

  it('saves enabled, the chosen job, threshold, and stop-loss', () => {
    const { onSave } = renderPanel();

    fireEvent.click(screen.getByLabelText('Enable automated strategy'));
    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(screen.getByRole('option', { name: /logistic_regression/ }));
    fireEvent.change(screen.getByLabelText('Confidence threshold percent'), {
      target: { value: '70' },
    });
    fireEvent.change(screen.getByLabelText('Default stop-loss percent'), {
      target: { value: '8' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith({
      enabled: true,
      trainingJobId: 'job-1',
      confidenceThresholdPct: '70',
      defaultStopLossPct: '8',
      leverage: '2',
    });
  });

  it('saves the leverage the user typed, as a plain fixed number', () => {
    const { onSave } = renderPanel();
    fireEvent.click(screen.getByLabelText('Enable automated strategy'));
    fireEvent.mouseDown(screen.getByLabelText('Training job'));
    fireEvent.click(screen.getByRole('option', { name: /logistic_regression/ }));
    fireEvent.change(screen.getByLabelText('Strategy leverage'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ leverage: '3' }));
  });

  it("starts from the account's own saved leverage", () => {
    renderPanel({ account: { ...ACCOUNT, strategy_leverage: '4' } });
    expect(screen.getByLabelText('Strategy leverage')).toHaveValue('4');
  });

  it("rejects a leverage below 1 or above the account's maximum", () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Strategy leverage'), { target: { value: '6' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(
      screen.getByText("Must be a number from 1 to 5 (this account's maximum)"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Strategy leverage'), { target: { value: '0.5' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Strategy leverage'), { target: { value: '5' } });
    expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled();
  });

  it('tells the user it trades both directions, and that the model is nearly always short', () => {
    renderPanel();
    expect(screen.getByText(/both directions/)).toBeInTheDocument();
    expect(screen.getByText(/short almost all the time/)).toBeInTheDocument();
  });

  it('rejects a stop-loss of 100 or more (would mean a price of zero)', () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Default stop-loss percent'), {
      target: { value: '100' },
    });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(
      screen.getByText('Must be a number greater than 0 and less than 100'),
    ).toBeInTheDocument();
  });

  it('accepts a confidence threshold of exactly 100', () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Confidence threshold percent'), {
      target: { value: '100' },
    });
    expect(screen.getByRole('button', { name: 'Save' })).not.toBeDisabled();
  });

  it('surfaces a save error', () => {
    renderPanel({ submitError: 'strategy_training_job_missing_symbol' });
    expect(screen.getByText('strategy_training_job_missing_symbol')).toBeInTheDocument();
  });

  it('renders skeletons while loading', () => {
    renderPanel({ account: undefined, isLoading: true });
    expect(screen.queryByText('Strategy disabled')).not.toBeInTheDocument();
  });
});

describe('StrategyPanel — feature-drift auto-pause banner', () => {
  it('shows a distinct error banner when the scheduler itself auto-paused for drift', () => {
    renderPanel({
      account: {
        ...ACCOUNT,
        strategy_enabled: false,
        strategy_paused_reason: 'feature_drift',
        strategy_paused_at: '2026-09-22T16:31:00Z',
      },
    });
    expect(screen.getByText(/auto-paused/i)).toBeInTheDocument();
    expect(screen.getByText(/feature drift detected/i)).toBeInTheDocument();
  });

  it('shows no drift banner for an ordinary human-disabled account', () => {
    renderPanel({
      account: { ...ACCOUNT, strategy_enabled: false, strategy_paused_reason: null },
    });
    expect(screen.queryByText(/feature drift detected/i)).not.toBeInTheDocument();
  });

  it('shows no drift banner for a healthy, enabled account', () => {
    renderPanel({
      account: { ...ACCOUNT, strategy_enabled: true, strategy_paused_reason: null },
    });
    expect(screen.queryByText(/feature drift detected/i)).not.toBeInTheDocument();
  });
});
