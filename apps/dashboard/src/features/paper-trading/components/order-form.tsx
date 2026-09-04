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
}

export interface OrderFormProps {
  onSubmit: (values: OrderFormValues) => void;
  submitting: boolean;
  hasAccount: boolean;
}

/**
 * Symbol, side, quantity — market orders only, no order-type selector at
 * all (this feature's own spec: long-only, market orders only, no
 * automation). Reuses `MarketSelector` (the same generic, data-driven
 * market picker the chart module uses) and `ConfirmActionDialog` (the
 * same "are you sure" pattern used elsewhere for a consequential action)
 * so placing an order — real cash spent or a real position reduced, even
 * if simulated — is never a single accidental click.
 */
export function OrderForm({ onSubmit, submitting, hasAccount }: OrderFormProps) {
  const [symbol, setSymbol] = useState<string | null>(null);
  const [side, setSide] = useState<PaperOrderSide>('buy');
  const [quantity, setQuantity] = useState('');
  const [confirming, setConfirming] = useState(false);

  const markets = useQuery({ queryKey: ['markets', 'list'], queryFn: fetchMarkets });

  const parsedQuantity = Number(quantity);
  const validQuantity =
    quantity.trim() !== '' && Number.isFinite(parsedQuantity) && parsedQuantity > 0;
  const canSubmit = hasAccount && Boolean(symbol) && validQuantity && !submitting;

  const handleConfirm = () => {
    if (!symbol || !validQuantity) return;
    setConfirming(false);
    onSubmit({ symbol, side, quantity });
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
        onChange={(_, next: PaperOrderSide | null) => next && setSide(next)}
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
        description="Fills immediately at the current market price, with a modeled slippage and fee applied — this cannot be undone."
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
