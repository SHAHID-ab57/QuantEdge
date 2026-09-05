'use client';

import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useState } from 'react';
import { EmptyStateNotice } from '@/components/empty-state-notice';
import { Section } from '@/components/section';
import { useTrainingJobs } from '@/features/ml-training/hooks/use-training-jobs-data';
import { AccountSummaryCard } from './components/account-summary-card';
import { CreateAccountDialog } from './components/create-account-dialog';
import { LiveDataChip } from './components/live-data-chip';
import { OrderForm, type OrderFormValues } from './components/order-form';
import { OrderHistoryTable } from './components/order-history-table';
import { PositionsTable } from './components/positions-table';
import { RiskSummaryPanel } from './components/risk-summary-panel';
import { SetThresholdsDialog } from './components/set-thresholds-dialog';
import { StrategyDecisionLogTable } from './components/strategy-decision-log-table';
import { StrategyPanel } from './components/strategy-panel';
import {
  useCreatePaperAccount,
  usePaperAccount,
  usePaperAccounts,
  usePaperOrders,
  usePaperPortfolioSummary,
  usePaperPositions,
  usePaperStrategyDecisions,
  usePaperTradingRisk,
  usePlacePaperOrder,
  useResumeTrading,
  useUpdatePaperStrategyConfig,
  useUpdatePositionThresholds,
} from './hooks/use-paper-trading-data';
import { usePaperTradingAccountStore } from './store/use-paper-trading-account-store';

const ORDERS_PAGE_SIZE = 10;
const DECISIONS_PAGE_SIZE = 10;

/**
 * A virtual trading account: place simulated market orders against real
 * prices, track positions, and compute PnL. Realistic execution is what
 * matters most (see `ARCHITECTURE.md` § "Paper Trading") — every fill's
 * own slippage/fee and price source are always visible, on every order,
 * never hidden behind a drill-down.
 *
 * There is no authentication anywhere on this platform, so "my account"
 * is a `localStorage`-remembered id (`usePaperTradingAccountStore`), with
 * Account History (`GET /paper-trading/accounts`) as the recovery path if
 * that's ever cleared or a different account is wanted.
 */
export function PaperTradingPage() {
  const { accountId, setAccountId } = usePaperTradingAccountStore();
  const [creating, setCreating] = useState(false);
  const [ordersPage, setOrdersPage] = useState(1);
  const [decisionsPage, setDecisionsPage] = useState(1);
  const [editingThresholdsFor, setEditingThresholdsFor] = useState<string | null>(null);

  const account = usePaperAccount(accountId);
  const summary = usePaperPortfolioSummary(accountId);
  const positions = usePaperPositions(accountId);
  const risk = usePaperTradingRisk(accountId);
  const orders = usePaperOrders(accountId, {
    limit: ORDERS_PAGE_SIZE,
    offset: (ordersPage - 1) * ORDERS_PAGE_SIZE,
  });
  const decisions = usePaperStrategyDecisions(accountId, {
    limit: DECISIONS_PAGE_SIZE,
    offset: (decisionsPage - 1) * DECISIONS_PAGE_SIZE,
  });
  const accounts = usePaperAccounts({ limit: 20, offset: 0 });
  const completedTrainingJobs = useTrainingJobs({ status: 'completed', limit: 100 });

  const createAccount = useCreatePaperAccount();
  const placeOrder = usePlacePaperOrder(accountId);
  const resumeTrading = useResumeTrading(accountId);
  const updateThresholds = useUpdatePositionThresholds(accountId);
  const updateStrategyConfig = useUpdatePaperStrategyConfig(accountId);

  // The remembered id might no longer exist (e.g. a fresh database) —
  // fall back to "no account" rather than a permanent error banner.
  const accountMissing = Boolean(accountId) && account.isError;
  const hasAccount = Boolean(accountId) && !accountMissing;

  const handleCreate = (values: { name: string | null; startingBalance: string }) => {
    createAccount.mutate(
      { name: values.name ?? undefined, starting_balance: values.startingBalance },
      {
        onSuccess: (created) => {
          setAccountId(created.id);
          setCreating(false);
        },
      },
    );
  };

  const handlePlaceOrder = (values: OrderFormValues) => {
    setOrdersPage(1);
    placeOrder.mutate({
      symbol: values.symbol,
      side: values.side,
      quantity: values.quantity,
      stop_loss_price: values.stopLossPrice,
      take_profit_price: values.takeProfitPrice,
    });
  };

  const handleSaveThresholds = (values: {
    stopLossPrice: string | null;
    takeProfitPrice: string | null;
  }) => {
    if (!editingThresholdsFor) return;
    updateThresholds.mutate(
      {
        symbol: editingThresholdsFor,
        body: { stop_loss_price: values.stopLossPrice, take_profit_price: values.takeProfitPrice },
      },
      { onSuccess: () => setEditingThresholdsFor(null) },
    );
  };

  const handleSaveStrategy = (values: {
    enabled: boolean;
    trainingJobId: string | null;
    confidenceThresholdPct: string;
    defaultStopLossPct: string;
  }) => {
    updateStrategyConfig.mutate({
      enabled: values.enabled,
      training_job_id: values.trainingJobId,
      confidence_threshold_pct: values.confidenceThresholdPct,
      default_stop_loss_pct: values.defaultStopLossPct,
    });
  };

  const editingPosition = positions.data?.positions.find((p) => p.symbol === editingThresholdsFor);

  const selectedAccountOption = accounts.data?.accounts.find((a) => a.id === accountId) ?? null;

  let resumeErrorMessage: string | null = null;
  if (resumeTrading.isError) {
    resumeErrorMessage =
      resumeTrading.error instanceof Error
        ? resumeTrading.error.message
        : 'Could not resume trading.';
  }

  let strategyErrorMessage: string | null = null;
  if (updateStrategyConfig.isError) {
    strategyErrorMessage =
      updateStrategyConfig.error instanceof Error
        ? updateStrategyConfig.error.message
        : 'Could not update the strategy.';
  }

  return (
    <Stack spacing={2}>
      <Section
        title="Account"
        subtitle="A virtual trading account — no real money is ever involved"
        action={<LiveDataChip />}
      >
        <Stack spacing={2}>
          {accounts.data && accounts.data.accounts.length > 0 ? (
            <Autocomplete
              size="small"
              options={accounts.data.accounts}
              value={selectedAccountOption}
              getOptionLabel={(option) => option.name ?? `Account ${option.id.slice(0, 8)}`}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              onChange={(_, next) => setAccountId(next?.id ?? null)}
              sx={{ maxWidth: 320 }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Account"
                  slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Account' } }}
                />
              )}
            />
          ) : null}

          {!hasAccount ? (
            <EmptyStateNotice
              icon={<AccountBalanceWalletIcon fontSize="small" color="disabled" />}
              title="No paper trading account yet"
              description="Open one to start placing simulated market orders against real prices."
            />
          ) : (
            <AccountSummaryCard
              accountName={account.data?.name ?? null}
              summary={summary.data}
              isLoading={summary.isLoading}
            />
          )}

          <Stack direction="row">
            <Button variant="outlined" size="small" onClick={() => setCreating(true)}>
              {hasAccount ? 'Open Another Account' : 'Open Account'}
            </Button>
          </Stack>

          {createAccount.isError ? (
            <Alert severity="error" role="alert">
              {createAccount.error instanceof Error
                ? createAccount.error.message
                : 'Could not open this account.'}
            </Alert>
          ) : null}
        </Stack>
      </Section>

      {hasAccount ? (
        <Section
          title="Risk"
          subtitle="Current exposure and drawdown against this account's own configured limits"
        >
          <RiskSummaryPanel
            data={risk.data}
            isLoading={risk.isLoading}
            onResume={() => resumeTrading.mutate()}
            resuming={resumeTrading.isPending}
            resumeError={resumeErrorMessage}
          />
        </Section>
      ) : null}

      <Section
        title="Place an Order"
        subtitle="Market orders only — fills immediately at the current real price, with a modeled slippage and fee"
      >
        <Stack spacing={2}>
          <OrderForm
            onSubmit={handlePlaceOrder}
            submitting={placeOrder.isPending}
            hasAccount={hasAccount}
          />
          {placeOrder.isError ? (
            <Alert severity="error" role="alert">
              {placeOrder.error instanceof Error
                ? placeOrder.error.message
                : 'Could not place this order.'}
            </Alert>
          ) : null}
        </Stack>
      </Section>

      <Section title="Positions" subtitle="Every symbol this account currently holds">
        <Stack spacing={1}>
          <PositionsTable
            data={positions.data}
            isLoading={positions.isLoading}
            onEditThresholds={setEditingThresholdsFor}
          />
          {updateThresholds.isError ? (
            <Alert severity="error" role="alert">
              {updateThresholds.error instanceof Error
                ? updateThresholds.error.message
                : 'Could not update stop-loss/take-profit.'}
            </Alert>
          ) : null}
        </Stack>
      </Section>

      <Section
        title="Order History"
        subtitle="Every filled order — fill price, source, and the slippage/fee actually applied"
      >
        <OrderHistoryTable
          data={orders.data}
          isLoading={orders.isLoading}
          page={ordersPage}
          limit={ORDERS_PAGE_SIZE}
          onPageChange={setOrdersPage}
        />
      </Section>

      {hasAccount ? (
        <Section
          title="Automated Strategy"
          subtitle="Optional, off by default — acts on a fresh prediction above a confidence threshold"
        >
          <Stack spacing={3}>
            <StrategyPanel
              account={account.data}
              isLoading={account.isLoading}
              completedJobs={completedTrainingJobs.data?.jobs ?? []}
              submitting={updateStrategyConfig.isPending}
              submitError={strategyErrorMessage}
              onSave={handleSaveStrategy}
            />
            <StrategyDecisionLogTable
              data={decisions.data}
              isLoading={decisions.isLoading}
              page={decisionsPage}
              limit={DECISIONS_PAGE_SIZE}
              onPageChange={setDecisionsPage}
            />
          </Stack>
        </Section>
      ) : null}

      <CreateAccountDialog
        open={creating}
        submitting={createAccount.isPending}
        onCancel={() => setCreating(false)}
        onCreate={handleCreate}
      />

      <SetThresholdsDialog
        open={editingThresholdsFor !== null}
        symbol={editingThresholdsFor}
        currentStopLossPrice={editingPosition?.stop_loss_price ?? null}
        currentTakeProfitPrice={editingPosition?.take_profit_price ?? null}
        submitting={updateThresholds.isPending}
        onCancel={() => setEditingThresholdsFor(null)}
        onSave={handleSaveThresholds}
      />
    </Stack>
  );
}
