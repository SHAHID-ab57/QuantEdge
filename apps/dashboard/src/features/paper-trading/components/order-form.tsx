'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ConfirmActionDialog } from '@/components/confirm-action-dialog';
import { MarketSelector } from '@/components/chart/market-selector';
import { InfoTooltip } from '@/components/info-tooltip';
import { fetchMarkets } from '@/lib/api/market';
import type { PaperOrderSide } from '@/types/api/paper-trading';

export interface OrderFormValues {
  symbol: string;
  side: PaperOrderSide;
  quantity: string;
  /** Buy only — omitted entirely (not sent) for a sell. */
  stopLossPrice?: string;
  takeProfitPrice?: string;
}

export interface OrderFormProps {
  onSubmit: (values: OrderFormValues) => void;
  submitting: boolean;
  hasAccount: boolean;
}

function isValidOptionalPrice(value: string): boolean {
  if (value.trim() === '') return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

/**
 * Symbol, side, quantity — market orders only, no order-type selector at
 * all (this feature's own spec: long-only, market orders only, no
 * automation). Reuses `MarketSelector` (the same generic, data-driven
 * market picker the chart module uses) and `ConfirmActionDialog` (the
 * same "are you sure" pattern used elsewhere for a consequential action)
 * so placing an order — real cash spent or a real position reduced, even
 * if simulated — is never a single accidental click.
 *
 * Stop-loss/take-profit are optional, buy-only fields — hidden and
 * cleared the instant the side is switched to sell, since a sell only
 * ever reduces/closes a position and has nothing left to protect (the
 * backend rejects the combination outright; this just avoids ever
 * offering it in the first place).
 */
export function OrderForm({ onSubmit, submitting, hasAccount }: OrderFormProps) {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [side, setSide] = useState<PaperOrderSide>('buy');
  const [quantity, setQuantity] = useState('');
  const [stopLossPrice, setStopLossPrice] = useState('');
  const [takeProfitPrice, setTakeProfitPrice] = useState('');
  const [confirming, setConfirming] = useState(false);

  const markets = useQuery({ queryKey: ['markets', 'list'], queryFn: fetchMarkets });

  const parsedQuantity = Number(quantity);
  const validQuantity =
    quantity.trim() !== '' && Number.isFinite(parsedQuantity) && parsedQuantity > 0;
  const validStopLoss = isValidOptionalPrice(stopLossPrice);
  const validTakeProfit = isValidOptionalPrice(takeProfitPrice);
  const canSubmit =
    hasAccount &&
    Boolean(symbol) &&
    validQuantity &&
    validStopLoss &&
    validTakeProfit &&
    !submitting;

  const handleSideChange = (next: PaperOrderSide | null) => {
    if (!next) return;
    setSide(next);
    if (next === 'sell') {
      // Stop-loss/take-profit only ever apply to a buy — clear them so a
      // value typed earlier can't be silently carried into a sell.
      setStopLossPrice('');
      setTakeProfitPrice('');
    }
  };

  const handleConfirm = () => {
    if (!symbol || !validQuantity || !validStopLoss || !validTakeProfit) return;
    setConfirming(false);
    onSubmit({
      symbol,
      side,
      quantity,
      stopLossPrice: side === 'buy' && stopLossPrice.trim() !== '' ? stopLossPrice : undefined,
      takeProfitPrice:
        side === 'buy' && takeProfitPrice.trim() !== '' ? takeProfitPrice : undefined,
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <MarketSelector
          markets={markets.data?.markets ?? []}
          value={symbol}
          onChange={setSymbol}
          loading={markets.isLoading}
        />
        <InfoTooltip
          label="Symbol"
          sections={[{ heading: 'What it is', body: 'The market this order trades.' }]}
        />
      </Stack>

      <ToggleButtonGroup
        value={side}
        exclusive
        onChange={(_, next: PaperOrderSide | null) => handleSideChange(next)}
        aria-label="Order side"
        size="small"
      >
        <ToggleButton value="buy" aria-label="Buy">
          Buy
        </ToggleButton>
        <ToggleButton value="sell" aria-label="Sell">
          Sell
        </ToggleButton>
      </ToggleButtonGroup>

      <Stack direction="row" spacing={0.5} alignItems="flex-start">
        <TextField
          fullWidth
          label="Quantity"
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          helperText="Base asset units — a market order, filled immediately at the current price."
          slotProps={{ htmlInput: { 'aria-label': 'Quantity', inputMode: 'decimal' } }}
        />
        <InfoTooltip
          label="Market order"
          sections={[
            {
              heading: 'What it is',
              body: 'Fills immediately at the current real price, with a modeled slippage and fee always applied — never a perfect, cost-free fill.',
            },
            {
              heading: 'Long-only',
              body: 'A sell can never exceed what this account actually holds — there is no shorting, margin, or leverage.',
            },
          ]}
        />
      </Stack>

      {side === 'buy' ? (
        <Stack direction="row" spacing={0.5} alignItems="flex-start">
          <TextField
            fullWidth
            label="Stop-loss (optional)"
            value={stopLossPrice}
            onChange={(event) => setStopLossPrice(event.target.value)}
            error={!validStopLoss}
            helperText={
              validStopLoss
                ? 'Auto-closes the position if price falls to or below this level.'
                : 'Must be a positive number.'
            }
            slotProps={{ htmlInput: { 'aria-label': 'Stop-loss price', inputMode: 'decimal' } }}
          />
          <TextField
            fullWidth
            label="Take-profit (optional)"
            value={takeProfitPrice}
            onChange={(event) => setTakeProfitPrice(event.target.value)}
            error={!validTakeProfit}
            helperText={
              validTakeProfit
                ? 'Auto-closes the position if price rises to or above this level.'
                : 'Must be a positive number.'
            }
            slotProps={{ htmlInput: { 'aria-label': 'Take-profit price', inputMode: 'decimal' } }}
          />
          <InfoTooltip
            label="Stop-loss / take-profit"
            sections={[
              {
                heading: 'What it is',
                body: 'Watches the live price and closes this position automatically the instant either level is crossed — no need to watch the market yourself.',
              },
              {
                heading: 'Validation',
                body: 'A stop-loss must be below the current price and a take-profit above it — a value that would trigger immediately is rejected.',
              },
              {
                heading: 'Realistic fills',
                body: 'A triggered close applies a wider modeled slippage than a manual order, honestly reflecting how a real stop behaves during a fast price move.',
              },
            ]}
          />
        </Stack>
      ) : null}

      {!hasAccount ? (
        <Alert severity="info" role="status">
          Open a paper trading account above before placing an order.
        </Alert>
      ) : null}

      <Button variant="contained" disabled={!canSubmit} onClick={() => setConfirming(true)}>
        {submitting
          ? 'Placing…'
          : `${side === 'buy' ? 'Buy' : 'Sell'}${symbol ? ` ${symbol}` : ''}`}
      </Button>

      <ConfirmActionDialog
        open={confirming}
        title={`${side === 'buy' ? 'Buy' : 'Sell'} ${quantity || '0'} ${symbol ?? ''}?`}
        description={
          side === 'buy' && (stopLossPrice.trim() !== '' || takeProfitPrice.trim() !== '')
            ? `Fills immediately at the current market price, with a modeled slippage and fee applied — this cannot be undone. Stop-loss/take-profit will be set on the resulting position.`
            : 'Fills immediately at the current market price, with a modeled slippage and fee applied — this cannot be undone.'
        }
        confirmLabel={side === 'buy' ? 'Buy' : 'Sell'}
        busyLabel="Placing…"
        color={side === 'buy' ? 'primary' : 'error'}
        busy={submitting}
        onCancel={() => setConfirming(false)}
        onConfirm={handleConfirm}
      />
    </Stack>
  );
}
