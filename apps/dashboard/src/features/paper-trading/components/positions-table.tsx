'use client';

import EditIcon from '@mui/icons-material/Edit';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { PaperPosition, PaperPositionListResponse } from '@/types/api/paper-trading';
import { formatSignedCurrency } from '../lib/format-pnl';

export interface PositionsTableProps {
  data: PaperPositionListResponse | undefined;
  isLoading: boolean;
  onEditThresholds: (symbol: string) => void;
}

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 2 }, (_, index) => (
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

function formatThreshold(value: string | null): string {
  return value === null ? '—' : `$${Number(value).toFixed(2)}`;
}

function PositionRow({
  position,
  onEditThresholds,
}: {
  position: PaperPosition;
  onEditThresholds: (symbol: string) => void;
}) {
  const unrealizedPnl = Number(position.unrealized_pnl);
  return (
    <TableRow hover>
      <TableCell>{position.symbol}</TableCell>
      <TableCell align="right">{Number(position.quantity)}</TableCell>
      <TableCell align="right">{`$${Number(position.average_entry_price).toFixed(2)}`}</TableCell>
      <TableCell align="right">{`$${Number(position.current_price).toFixed(2)}`}</TableCell>
      <TableCell>
        <Chip size="small" variant="outlined" label={position.price_source} />
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(unrealizedPnl) }}>
        {formatSignedCurrency(unrealizedPnl)}
      </TableCell>
      <TableCell align="right">
        {formatThreshold(position.stop_loss_price)} / {formatThreshold(position.take_profit_price)}
      </TableCell>
      <TableCell align="right">
        <Tooltip title="Set stop-loss / take-profit">
          <IconButton
            size="small"
            aria-label={`Edit stop-loss/take-profit for ${position.symbol}`}
            onClick={() => onEditThresholds(position.symbol)}
          >
            <EditIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

/** An account's currently-open positions, each marked to the same live
 * price a fill would use — never a slippage-adjusted hypothetical exit.
 * The "SL / TP" column shows both thresholds (a dash when unset); the
 * edit action opens `SetThresholdsDialog` to set/update/clear either. */
export function PositionsTable({ data, isLoading, onEditThresholds }: PositionsTableProps) {
  const positions = data?.positions ?? [];

  return (
    <Paper variant="outlined">
      <TableContainer>
        <Table aria-label="Open positions table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell align="right">Quantity</TableCell>
              <TableCell align="right">Avg Entry</TableCell>
              <TableCell align="right">Current Price</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right">Unrealized PnL</TableCell>
              <TableCell align="right">SL / TP</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && !data ? (
              <LoadingRows />
            ) : (
              positions.map((position) => (
                <PositionRow
                  key={position.symbol}
                  position={position}
                  onEditThresholds={onEditThresholds}
                />
              ))
            )}
            {!isLoading && positions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No open positions — place a buy order above to open one.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
}
