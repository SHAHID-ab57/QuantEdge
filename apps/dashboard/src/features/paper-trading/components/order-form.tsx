'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ConfirmActionDialog } from '@/components/confirm-action-dialog';
import { MarketSelector } from '@/components/chart/market-selector';
import { InfoTooltip } from '@/components/info-tooltip';
import { fetchMarkets } from '@/lib/api/market';
import type { PaperOrderSide, PaperPosition } from '@/types/api/paper-trading';
import { describeOrderEffect, effectSentence } from '../lib/order-effect';

export interface OrderFormValues {
  symbol: string;
  side: PaperOrderSide;
  quantity: string;
  /** Only when this order opens a new position above 1x; omitted otherwise. */
  leverage?: string;
  /** Only when ticked; omitted (not `false`) otherwise. */
  reduceOnly?: boolean;
  /** Only on an order that opens or adds — omitted entirely otherwise. */
  stopLossPrice?: string;
  takeProfitPrice?: string;
}

export interface OrderFormProps {
  onSubmit: (values: OrderFormValues) => void;
  submitting: boolean;
  hasAccount: boolean;
  /** The account's open positions, so the form can say what an order will do to them. */
  positions?: PaperPosition[];
  /** The account's own leverage ceiling; 1 (no leverage) until it is known. */
  maxLeverage?: number;
}

const MIN_LEVERAGE = 1;

function isValidOptionalPrice(value: string): boolean {
  if (value.trim() === '') return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

/**
 * Symbol, side, quantity, and (for a position this order opens) leverage —
 * market orders only, no order-type selector at all. Reuses `MarketSelector`
 * (the same generic, data-driven market picker the chart module uses) and
 * `ConfirmActionDialog` (the same "are you sure" pattern used elsewhere for a
 * consequential action) so placing an order — real margin posted or a real
 * position reduced, even if simulated — is never a single accidental click.
 *
 * A buy opens/adds to a long or reduces a short; a sell opens/adds to a
 * short or reduces a long. The form works out which of those the order
 * would be against the account's open positions (`describeOrderEffect`) and
 * says so, and refuses one larger than the position it reduces (the backend
 * rejects that too — it would carry the position through zero in one step).
 * Leverage is chosen only when an order opens a position (it is fixed for
 * that position's life); an order that adds shows the position's own, and a
 * reducing order has none to choose.
 *
 * Stop-loss/take-profit are optional and only offered on an order that opens
 * or adds — a reducing order has nothing left to protect — with helper text
 * that follows the side of the position they would protect.
 */
export function OrderForm({
  onSubmit,
  submitting,
  hasAccount,
  positions = [],
  maxLeverage = MIN_LEVERAGE,
}: OrderFormProps) {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [side, setSide] = useState<PaperOrderSide>('buy');
  const [quantity, setQuantity] = useState('');
  const [stopLossPrice, setStopLossPrice] = useState('');
  const [takeProfitPrice, setTakeProfitPrice] = useState('');
  const [leverage, setLeverage] = useState('1');
  const [reduceOnly, setReduceOnly] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const markets = useQuery({ queryKey: ['markets', 'list'], queryFn: fetchMarkets });

  const parsedQuantity = Number(quantity);
  const validQuantity =
    quantity.trim() !== '' && Number.isFinite(parsedQuantity) && parsedQuantity > 0;
  const validStopLoss = isValidOptionalPrice(stopLossPrice);
  const validTakeProfit = isValidOptionalPrice(takeProfitPrice);

  const heldPosition = symbol ? positions.find((p) => p.symbol === symbol) : undefined;
  const effect = describeOrderEffect(side, validQuantity ? parsedQuantity : 0, heldPosition);
  const opensOrAdds = effect.kind === 'open' || effect.kind === 'add';
  const opens = effect.kind === 'open';

  // Leverage is only chosen for a position this order opens (it is fixed for
  // that position's life); anything else acts at the position's own.
  const parsedLeverage = Number(leverage);
  const validLeverage =
    !opens ||
    (leverage.trim() !== '' &&
      Number.isFinite(parsedLeverage) &&
      parsedLeverage >= MIN_LEVERAGE &&
      parsedLeverage <= maxLeverage);
  const reduceOnlyConflict = reduceOnly && opensOrAdds;
  const showThresholds = opensOrAdds && !reduceOnly;
  const isRisky = opensOrAdds && (effect.positionSide === 'short' || (opens && parsedLeverage > 1));

  const canSubmit =
    hasAccount &&
    Boolean(symbol) &&
    validQuantity &&
    validStopLoss &&
    validTakeProfit &&
    validLeverage &&
    effect.kind !== 'flip' &&
    !reduceOnlyConflict &&
    !submitting;

  const handleSideChange = (next: PaperOrderSide | null) => {
    if (!next) return;
    setSide(next);
    // Thresholds are validated against the side of the position they protect;
    // a value typed for the other side would be wrong, so never carry it over.
    setStopLossPrice('');
    setTakeProfitPrice('');
  };

  const handleConfirm = () => {
    if (!symbol || !canSubmit) return;
    setConfirming(false);
    onSubmit({
      symbol,
      side,
      quantity,
      leverage: opens && parsedLeverage > 1 ? leverage : undefined,
      reduceOnly: reduceOnly ? true : undefined,
      stopLossPrice: showThresholds && stopLossPrice.trim() !== '' ? stopLossPrice : undefined,
      takeProfitPrice:
        showThresholds && takeProfitPrice.trim() !== '' ? takeProfitPrice : undefined,
    });
  };

  const stopHelper =
    effect.positionSide === 'short'
      ? 'Auto-closes the position if price rises to or above this level.'
      : 'Auto-closes the position if price falls to or below this level.';
  const takeHelper =
    effect.positionSide === 'short'
      ? 'Auto-closes the position if price falls to or below this level.'
      : 'Auto-closes the position if price rises to or above this level.';

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
          helperText={
            symbol
              ? effectSentence(effect, symbol)
              : 'Base asset units — a market order, filled immediately at the current price.'
          }
          error={effect.kind === 'flip'}
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
              heading: 'Long and short',
              body: 'One net position per market. A buy opens or adds to a long, or reduces a short; a sell opens or adds to a short, or reduces a long. An order larger than the position it reduces is rejected rather than flipped through zero.',
            },
          ]}
        />
      </Stack>

      {opens ? (
        <Stack direction="row" spacing={0.5} alignItems="flex-start">
          <TextField
            fullWidth
            label="Leverage (x)"
            value={leverage}
            onChange={(event) => setLeverage(event.target.value)}
            error={!validLeverage}
            helperText={
              validLeverage
                ? `Isolated margin — this account allows up to ${maxLeverage}x. 1x posts the whole notional.`
                : `Enter a leverage from ${MIN_LEVERAGE} to ${maxLeverage}.`
            }
            slotProps={{ htmlInput: { 'aria-label': 'Leverage', inputMode: 'decimal' } }}
          />
          <InfoTooltip
            label="Leverage"
            sections={[
              {
                heading: 'What it is',
                body: 'Posts notional ÷ leverage of your cash as margin for this position. Leverage is fixed for the life of the position.',
              },
              {
                heading: 'Risk',
                body: 'Higher leverage puts the liquidation price closer to the entry price. If the mark price reaches it, the whole margin is forfeited. Leverage does not raise the position-size or exposure limits, which are measured on notional.',
              },
            ]}
          />
        </Stack>
      ) : null}
      {effect.kind === 'add' && heldPosition ? (
        <Typography variant="caption" color="text.secondary">
          Adds at this position&apos;s own leverage: {Number(heldPosition.leverage)}x.
        </Typography>
      ) : null}

      <FormControlLabel
        control={
          <Checkbox
            checked={reduceOnly}
            onChange={(event) => setReduceOnly(event.target.checked)}
            slotProps={{ input: { 'aria-label': 'Reduce only' } }}
          />
        }
        label="Reduce only"
      />
      {reduceOnlyConflict ? (
        <Alert severity="warning" role="status">
          Reduce-only can only shrink an existing position — this order would open or add to one.
        </Alert>
      ) : null}

      {showThresholds ? (
        <Stack direction="row" spacing={0.5} alignItems="flex-start">
          <TextField
            fullWidth
            label="Stop-loss (optional)"
            value={stopLossPrice}
            onChange={(event) => setStopLossPrice(event.target.value)}
            error={!validStopLoss}
            helperText={validStopLoss ? stopHelper : 'Must be a positive number.'}
            slotProps={{ htmlInput: { 'aria-label': 'Stop-loss price', inputMode: 'decimal' } }}
          />
          <TextField
            fullWidth
            label="Take-profit (optional)"
            value={takeProfitPrice}
            onChange={(event) => setTakeProfitPrice(event.target.value)}
            error={!validTakeProfit}
            helperText={validTakeProfit ? takeHelper : 'Must be a positive number.'}
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
                body: 'For a long, a stop-loss must be below the current price and a take-profit above it; for a short, the reverse. A value that would trigger immediately is rejected, and so is a stop-loss beyond the position’s liquidation price (it could never fire: the position is liquidated first).',
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

      {isRisky ? (
        <Alert severity="warning" role="status">
          {effect.positionSide === 'short' ? 'A short' : 'A leveraged'} position can be liquidated:
          if the mark price reaches its liquidation price, the whole margin posted is forfeited. Its
          liquidation price is shown on the position once it is open.
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
        description={[
          effectSentence(effect, symbol),
          opens && parsedLeverage > 1 ? `Leverage ${parsedLeverage}x (isolated margin).` : null,
          'Fills immediately at the current market price, with a modeled slippage and fee applied — this cannot be undone.',
          showThresholds && (stopLossPrice.trim() !== '' || takeProfitPrice.trim() !== '')
            ? 'Stop-loss/take-profit will be set on the resulting position.'
            : null,
        ]
          .filter(Boolean)
          .join(' ')}
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
