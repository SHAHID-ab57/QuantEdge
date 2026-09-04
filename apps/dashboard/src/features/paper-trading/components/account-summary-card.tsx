'use client';

import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { PortfolioSummary } from '@/types/api/paper-trading';
import { formatSignedCurrency } from '../lib/format-pnl';

export interface AccountSummaryCardProps {
  accountName: string | null;
  summary: PortfolioSummary | undefined;
  isLoading: boolean;
}

function pnlColor(value: number): 'success.main' | 'error.main' | 'text.primary' {
  if (value > 0) return 'success.main';
  if (value < 0) return 'error.main';
  return 'text.primary';
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Stack spacing={0.25} sx={{ minWidth: 140 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6" sx={{ color, fontWeight: 700 }}>
        {value}
      </Typography>
    </Stack>
  );
}

/**
 * Balance, realized PnL, unrealized PnL, and total equity — the account's
 * own headline numbers. Realized and unrealized PnL are colored green
 * (gain), red (loss), or neutral (exactly zero) so the sign is legible at
 * a glance, never just implied by a bare `-` prefix.
 */
export function AccountSummaryCard({ accountName, summary, isLoading }: AccountSummaryCardProps) {
  if (isLoading || !summary) {
    return (
      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} variant="text" width={140} height={48} />
        ))}
      </Stack>
    );
  }

  const realizedPnl = Number(summary.realized_pnl);
  const unrealizedPnl = Number(summary.unrealized_pnl);

  return (
    <Stack spacing={1}>
      {accountName ? (
        <Typography variant="subtitle2" color="text.secondary">
          {accountName}
        </Typography>
      ) : null}
      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
        <Metric label="Cash Balance" value={`$${Number(summary.balance).toFixed(2)}`} />
        <Metric
          label="Realized PnL"
          value={formatSignedCurrency(realizedPnl)}
          color={pnlColor(realizedPnl)}
        />
        <Metric
          label="Unrealized PnL"
          value={formatSignedCurrency(unrealizedPnl)}
          color={pnlColor(unrealizedPnl)}
        />
        <Metric label="Total Equity" value={`$${Number(summary.total_equity).toFixed(2)}`} />
      </Stack>
    </Stack>
  );
}
