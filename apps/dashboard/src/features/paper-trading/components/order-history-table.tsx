'use client';

import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { PaperOrder, PaperOrderListResponse } from '@/types/api/paper-trading';
import { formatSignedCurrency } from '../lib/format-pnl';

export interface OrderHistoryTableProps {
  data: PaperOrderListResponse | undefined;
  isLoading: boolean;
  page: number;
  limit: number;
  onPageChange: (page: number) => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 3 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={10}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

function triggerLabel(reason: PaperOrder['trigger_reason']): string {
  if (reason === 'stop_loss') return 'Stop-Loss';
  if (reason === 'take_profit') return 'Take-Profit';
  if (reason === 'liquidation') return 'Liquidation';
  return 'Manual';
}

function triggerColor(reason: PaperOrder['trigger_reason']): 'default' | 'error' | 'warning' {
  if (reason === null) return 'default';
  return reason === 'liquidation' ? 'error' : 'warning';
}

function triggerExplanation(order: PaperOrder): string {
  if (order.trigger_reason === null) return 'Placed manually';
  if (order.trigger_reason === 'liquidation') {
    const basis =
      order.trigger_price_basis === 'last_fallback'
        ? ' (no mark price was available, so the last traded price stood in)'
        : ' on the mark price';
    const gap = order.gapped_through_bankruptcy
      ? ' The price had already gapped past the bankruptcy price; the loss is still capped at the margin posted.'
      : '';
    return `Liquidated${basis} — the position's whole margin (${'$'}${Number(order.margin_applied).toFixed(2)}) was forfeited.${gap}`;
  }
  return `Closed automatically — its ${triggerLabel(order.trigger_reason).toLowerCase()} price was crossed`;
}

function pnlColor(value: number): 'success.main' | 'error.main' | 'text.primary' {
  if (value > 0) return 'success.main';
  if (value < 0) return 'error.main';
  return 'text.primary';
}

function OrderRow({ order }: { order: PaperOrder }) {
  const realizedPnl = order.realized_pnl === null ? null : Number(order.realized_pnl);
  return (
    <TableRow hover>
      <TableCell>{new Date(order.fill_time).toLocaleString()}</TableCell>
      <TableCell>{order.symbol}</TableCell>
      <TableCell>
        <Chip
          size="small"
          color={order.side === 'buy' ? 'success' : 'error'}
          label={order.side.toUpperCase()}
        />
      </TableCell>
      <TableCell>
        <Chip
          size="small"
          variant="outlined"
          color={order.position_side === 'long' ? 'success' : 'error'}
          label={`${order.position_side === 'long' ? 'Long' : 'Short'} ${Number(order.leverage)}x${order.reduce_only ? ' · reduce' : ''}`}
        />
      </TableCell>
      <TableCell>
        <Tooltip title={triggerExplanation(order)}>
          <Chip
            size="small"
            variant={order.trigger_reason === null ? 'outlined' : 'filled'}
            color={triggerColor(order.trigger_reason)}
            label={triggerLabel(order.trigger_reason)}
          />
        </Tooltip>
      </TableCell>
      <TableCell align="right">{Number(order.quantity)}</TableCell>
      <TableCell align="right">${Number(order.fill_price).toFixed(4)}</TableCell>
      <TableCell>
        <Tooltip
          title={
            order.is_stale_price
              ? `Priced from a ${order.price_source} quote observed ${new Date(order.price_observed_at).toLocaleString()} — older than this platform's staleness threshold`
              : `Priced from a ${order.price_source} quote`
          }
        >
          <Chip
            size="small"
            variant="outlined"
            label={order.price_source}
            icon={order.is_stale_price ? <WarningAmberIcon fontSize="small" /> : undefined}
            color={order.is_stale_price ? 'warning' : 'default'}
          />
        </Tooltip>
      </TableCell>
      <TableCell align="right">
        ${Number(order.slippage_applied).toFixed(4)} / ${Number(order.fee_applied).toFixed(4)}
      </TableCell>
      <TableCell
        align="right"
        sx={{ color: realizedPnl === null ? undefined : pnlColor(realizedPnl) }}
      >
        {realizedPnl === null ? (
          <Typography variant="caption" color="text.secondary">
            —
          </Typography>
        ) : (
          formatSignedCurrency(realizedPnl)
        )}
      </TableCell>
    </TableRow>
  );
}

/**
 * Every filled order for this account, most recent first — fill price,
 * price source, and the slippage/fee actually applied are always visible
 * columns, never hidden detail behind a drill-down (this feature's own
 * spec: realistic execution is what matters most, so its cost must be as
 * visible as the fill itself). A stale-priced fill (the fallback candle
 * was already older than the staleness threshold) is marked with a
 * warning chip, not silently presented as current. The "Trigger" column
 * makes a market-triggered auto-close (a filled chip: `warning`-colored
 * "Stop-Loss"/"Take-Profit", `error`-colored "Liquidation") clearly distinct from an ordinary,
 * manually-placed order (an outlined "Manual" chip) — never the same
 * plain row for both.
 */
export function OrderHistoryTable({
  data,
  isLoading,
  page,
  limit,
  onPageChange,
}: OrderHistoryTableProps) {
  const orders = data?.orders ?? [];
  const total = data?.total ?? 0;

  return (
    <Paper variant="outlined">
      <TableContainer sx={{ maxHeight: 420 }}>
        <Table stickyHeader aria-label="Order history table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Fill Time</TableCell>
              <TableCell>Symbol</TableCell>
              <TableCell>Side</TableCell>
              <TableCell>Position</TableCell>
              <TableCell>Trigger</TableCell>
              <TableCell align="right">Quantity</TableCell>
              <TableCell align="right">Fill Price</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right">Slippage / Fee</TableCell>
              <TableCell align="right">Realized PnL</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              orders.map((order) => <OrderRow key={order.id} order={order} />)
            )}
            {!isLoading && orders.length === 0 ? (
              <TableRow>
                <TableCell colSpan={10} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No orders yet — place one above, and it will appear here.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        component="div"
        count={total}
        page={page - 1}
        onPageChange={(_, nextPage) => onPageChange(nextPage + 1)}
        rowsPerPage={limit}
        rowsPerPageOptions={[]}
        labelRowsPerPage=""
      />
    </Paper>
  );
}
