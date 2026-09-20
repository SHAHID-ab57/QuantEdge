'use client';

import EditIcon from '@mui/icons-material/Edit';
import Button from '@mui/material/Button';
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
  onClosePosition: (position: PaperPosition) => void;
}

const COLUMN_COUNT = 11;

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 2 }, (_, index) => (
        <TableRow key={index}>
          <TableCell colSpan={COLUMN_COUNT}>
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

/** How close a position is to liquidation, for coloring: a position within 10%
 * of it is the one a person needs to notice. */
const LIQUIDATION_WARNING_DISTANCE_PCT = 10;

function LiquidationCell({ position }: { position: PaperPosition }) {
  if (position.liquidation_price === null) {
    return (
      <Tooltip title="An unleveraged long has posted its whole notional, so it can only reach zero — it cannot be liquidated.">
        <Typography variant="body2" color="text.secondary" component="span">
          —
        </Typography>
      </Tooltip>
    );
  }
  const distance =
    position.liquidation_distance_pct === null ? null : Number(position.liquidation_distance_pct);
  const near = distance !== null && distance < LIQUIDATION_WARNING_DISTANCE_PCT;
  return (
    <Tooltip title="The mark price at which this position is liquidated and its whole margin forfeited.">
      <Typography
        variant="body2"
        component="span"
        sx={{ color: near ? 'error.main' : 'text.primary', fontWeight: near ? 700 : undefined }}
      >
        {`$${Number(position.liquidation_price).toFixed(2)}`}
        {distance === null ? '' : ` (${distance.toFixed(1)}% away)`}
      </Typography>
    </Tooltip>
  );
}

function PositionRow({
  position,
  onEditThresholds,
  onClosePosition,
}: {
  position: PaperPosition;
  onEditThresholds: (symbol: string) => void;
  onClosePosition: (position: PaperPosition) => void;
}) {
  const unrealizedPnl = Number(position.unrealized_pnl);
  return (
    <TableRow hover>
      <TableCell>{position.symbol}</TableCell>
      <TableCell>
        <Chip
          size="small"
          color={position.side === 'long' ? 'success' : 'error'}
          label={position.side === 'long' ? 'Long' : 'Short'}
        />
      </TableCell>
      <TableCell align="right">{Number(position.quantity)}</TableCell>
      <TableCell align="right">{`${Number(position.leverage)}x`}</TableCell>
      <TableCell align="right">{`$${Number(position.margin).toFixed(2)}`}</TableCell>
      <TableCell align="right">{`$${Number(position.average_entry_price).toFixed(2)}`}</TableCell>
      <TableCell align="right">{`$${Number(position.current_price).toFixed(2)}`}</TableCell>
      <TableCell>
        <Chip size="small" variant="outlined" label={position.price_source} />
      </TableCell>
      <TableCell align="right" sx={{ color: pnlColor(unrealizedPnl) }}>
        {formatSignedCurrency(unrealizedPnl)}
      </TableCell>
      <TableCell align="right">
        <LiquidationCell position={position} />
      </TableCell>
      <TableCell align="right">
        {formatThreshold(position.stop_loss_price)} / {formatThreshold(position.take_profit_price)}
      </TableCell>
      <TableCell align="right">
        <Button
          size="small"
          variant="outlined"
          aria-label={`Close ${position.symbol} ${position.side} position`}
          onClick={() => onClosePosition(position)}
          sx={{ mr: 0.5 }}
        >
          Close
        </Button>
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
 * Each row says whether it is a long or a short, its leverage and the isolated
 * margin posted, and its liquidation price (a dash for an unleveraged long,
 * which cannot be liquidated; red when the price is within 10% of it). The
 * "SL / TP" column shows both thresholds (a dash when unset); the edit action
 * opens `SetThresholdsDialog` to set/update/clear either, and "Close" sends a
 * reduce-only order for the whole position. */
export function PositionsTable({
  data,
  isLoading,
  onEditThresholds,
  onClosePosition,
}: PositionsTableProps) {
  const positions = data?.positions ?? [];

  return (
    <Paper variant="outlined">
      <TableContainer>
        <Table aria-label="Open positions table" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Symbol</TableCell>
              <TableCell>Side</TableCell>
              <TableCell align="right">Quantity</TableCell>
              <TableCell align="right">Leverage</TableCell>
              <TableCell align="right">Margin</TableCell>
              <TableCell align="right">Avg Entry</TableCell>
              <TableCell align="right">Current Price</TableCell>
              <TableCell>Source</TableCell>
              <TableCell align="right">Unrealized PnL</TableCell>
              <TableCell align="right">Liq. Price</TableCell>
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
                  onClosePosition={onClosePosition}
                />
              ))
            )}
            {!isLoading && positions.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLUMN_COUNT} align="center" sx={{ py: 4 }}>
                  <Typography variant="body2" color="text.secondary" role="status">
                    No open positions — place an order above to open one.
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
