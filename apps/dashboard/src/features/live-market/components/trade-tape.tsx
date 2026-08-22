'use client';

import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { formatDecimal } from '@/features/history/lib/format';
import type { LiveTradeData } from '@/types/api/market-stream';

export interface TradeTapeProps {
  trades: LiveTradeData[];
  isConnecting: boolean;
  /** Cap applied upstream by `useMarketStream`, shown so the cap is not a mystery. */
  maxTrades: number;
}

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

type TradeSide = 'buy' | 'sell' | 'unknown';

/**
 * The backend normalizes the exchange's buyer-role flag into a real
 * aggressor side (see `app/marketdata/normalizer.py`), but the wire type is
 * a plain string, so anything unexpected degrades to "unknown" rather than
 * being coerced into a buy or a sell.
 */
function tradeSide(trade: LiveTradeData): TradeSide {
  if (trade.side === 'buy' || trade.side === 'sell') {
    return trade.side;
  }
  return 'unknown';
}

const SIDE_COLOR: Record<TradeSide, string> = {
  buy: 'success.main',
  sell: 'error.main',
  unknown: 'text.secondary',
};

const SIDE_LABEL: Record<TradeSide, string> = {
  buy: 'Buy',
  sell: 'Sell',
  unknown: 'Unknown',
};

/**
 * Newest-first trade tape. `trades` is capped upstream by `useMarketStream`'s
 * `maxTrades` option so neither the buffer nor this table grows without
 * bound on a busy market.
 *
 * Rows are tinted by aggressor side — a buy means the taker lifted the
 * offer. This is the exchange's own classification, not one inferred from
 * price movement.
 */
function TradeTapeInner({ trades, isConnecting, maxTrades }: TradeTapeProps) {
  if (isConnecting && trades.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 2.5 }}>
        <Typography variant="h6" component="h2" gutterBottom>
          Trade Tape
        </Typography>
        <Skeleton
          variant="rounded"
          height={200}
          role="status"
          aria-label="Connecting to trade stream"
        />
      </Paper>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack direction="row" spacing={1} alignItems="baseline" sx={{ mb: 1 }}>
        <Typography variant="h6" component="h2">
          Trade Tape
        </Typography>
        <Typography variant="caption" color="text.secondary">
          newest first · last {maxTrades}
        </Typography>
      </Stack>
      {trades.length === 0 ? (
        <Alert severity="info" role="status">
          Connected, but no trades have printed yet. Quiet markets can go minutes between trades.
        </Alert>
      ) : (
        <TableContainer sx={{ maxHeight: 360 }}>
          <Table size="small" stickyHeader aria-label="Recent trades">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell align="right">Price</TableCell>
                <TableCell align="right">Quantity</TableCell>
                <TableCell>Side</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {trades.map((trade, index) => {
                const side = tradeSide(trade);
                return (
                  <TableRow key={`${trade.event_time}-${index}`} hover>
                    <TableCell sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {timeFormatter.format(new Date(trade.event_time))}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: SIDE_COLOR[side],
                        fontWeight: 600,
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {formatDecimal(trade.price)}
                    </TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {formatDecimal(trade.size)}
                    </TableCell>
                    <TableCell>
                      <Box component="span" sx={{ color: SIDE_COLOR[side], fontWeight: 600 }}>
                        {SIDE_LABEL[side]}
                      </Box>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Paper>
  );
}

export const TradeTape = memo(TradeTapeInner);
