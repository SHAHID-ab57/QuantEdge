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
          <TableCell colSpan={8}>
            <Skeleton variant="text" />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
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
 * warning chip, not silently presented as current.
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
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
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
