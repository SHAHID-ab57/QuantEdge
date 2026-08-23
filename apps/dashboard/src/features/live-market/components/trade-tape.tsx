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
import { memo, useCallback, useRef, useState, type ReactNode, type UIEvent } from 'react';
import { formatDecimal } from '@/features/history/lib/format';
import type { LiveTradeData } from '@/types/api/market-stream';

export interface TradeTapeProps {
  trades: LiveTradeData[];
  isConnecting: boolean;
  /** Cap applied upstream by `useMarketStream`, shown so the cap is not a mystery. */
  maxTrades: number;
  /**
   * Adds a Trade Value (price × quantity) column — off by default so the
   * Live Market Dashboard's existing four-column tape is unchanged. The
   * Live Trade Analytics dashboard turns this on, since notional value is
   * one of its explicit required columns.
   */
  showTradeValue?: boolean;
  /**
   * A trade whose notional value (price × size) is at or above this is
   * tinted and marked "Large" — off by default (`undefined`) so the Live
   * Market Dashboard's tape is unchanged. The Live Trade Analytics
   * dashboard passes its session average notional times a fixed multiplier
   * (`lib/trade-highlight.ts`).
   */
  largeTradeThreshold?: number;
  /**
   * Renders only the rows near the viewport once the list is long enough to
   * be worth it (see `VIRTUALIZE_THRESHOLD`). Off by default: the Live
   * Market Dashboard's tape is short and gains nothing from it.
   */
  virtualize?: boolean;
  /** Rendered in the header row, right-aligned — the analytics dashboard puts its CSV export here. */
  action?: ReactNode;
  /**
   * Rendered beside the "Trade Value" column header — the analytics
   * dashboard passes its `MetricInfo` button, so the column's meaning is
   * explained in place. Only shown when `showTradeValue` is on.
   */
  valueColumnInfo?: ReactNode;
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

/** Notional value (price × quantity); `NaN` when either field is unparseable. */
function tradeValue(trade: LiveTradeData): number {
  const value = Number(trade.price) * Number(trade.size);
  return Number.isFinite(value) ? value : NaN;
}

/** Height of one rendered row, in px — the basis of every virtualization offset. */
const ROW_HEIGHT = 33;
/** Height of the scrollable body. */
const BODY_HEIGHT = 360;
/** Rows rendered above and below the viewport, so a fast scroll doesn't reveal blank space. */
const OVERSCAN = 6;
/** Below this many rows, virtualization costs more than it saves. */
const VIRTUALIZE_THRESHOLD = 60;

/**
 * Assigns each trade object a stable, monotonically increasing key the
 * first time it's seen, keyed by object identity (every trade the socket
 * delivers is a distinct object, created once by `JSON.parse` + Zod
 * validation and never mutated afterward — see `use-market-stream.ts`).
 *
 * This matters for more than tidiness: `trades` is newest-first, so a new
 * trade is *unshifted* onto the front and every existing trade's array
 * index shifts by one. Keying rows by `${event_time}-${index}` (the
 * previous scheme) therefore changed *every* row's key on *every* new
 * trade, making React discard and remount the entire table body each time —
 * the exact "unnecessary re-render" this dashboard's performance pass set
 * out to find. Keying by a per-object id fixes both problems at once: only
 * the genuinely new row mounts fresh (which is also what makes the CSS
 * enter animation below fire only for it, not for rows that were already
 * on screen), and a `WeakMap` needs no manual cleanup — entries for trades
 * that fall out of `maxTrades` are reclaimed by the garbage collector once
 * nothing else references them.
 */
function useTradeKeys(trades: LiveTradeData[]): number[] {
  const idsRef = useRef(new WeakMap<LiveTradeData, number>());
  const nextIdRef = useRef(0);
  return trades.map((trade) => {
    let id = idsRef.current.get(trade);
    if (id === undefined) {
      id = nextIdRef.current;
      nextIdRef.current += 1;
      idsRef.current.set(trade, id);
    }
    return id;
  });
}

interface TradeTapeRowProps {
  trade: LiveTradeData;
  isLarge: boolean;
  /**
   * Drives zebra striping. Derived from the row's *stable per-trade key*,
   * never from its array index — striping by index would flip this prop for
   * every row each time a trade is prepended (which shifts all indices by
   * one), forcing React to re-render the entire tape on every single trade
   * and defeating the memoization below entirely. That is not theoretical:
   * it was measured at 101 row renders per trade before this was changed
   * (see `trade-tape.render.test.tsx`).
   *
   * The trade-off: keys are consecutive for consecutively-arriving trades,
   * so stripes alternate normally — but a filtered-out or capped-off trade
   * leaves a gap in the key sequence, which can put two same-shade rows
   * next to each other. A cosmetic imperfection in a filtered view is a
   * fair price for not re-rendering a hundred rows several times a second.
   */
  isStriped: boolean;
  showTradeValue: boolean;
}

/**
 * One row, memoized on its own props. Every prop is a primitive except
 * `trade`, which is a stable, never-mutated object, so React's default
 * shallow comparison is exactly right here — no custom comparator needed
 * (unlike the Order Book's rows, whose props are recomputed numbers).
 *
 * The practical effect: when a new trade arrives and the parent re-renders,
 * the ~100 rows that didn't change skip rendering entirely.
 */
function TradeTapeRowInner({ trade, isLarge, isStriped, showTradeValue }: TradeTapeRowProps) {
  const side = tradeSide(trade);
  const value = tradeValue(trade);
  // Sticky cells need an opaque background of their own, or the rows
  // scrolling underneath show through them — so each row variant's
  // effective background has to be restated here as a solid colour.
  let stickyBackground = 'var(--mui-palette-background-paper)';
  if (isLarge) {
    stickyBackground = 'rgb(70, 52, 12)';
  } else if (isStriped) {
    stickyBackground = 'rgb(23, 30, 44)';
  }

  return (
    <TableRow
      hover
      sx={{
        animation: 'tradeRowEnter 900ms ease-out',
        transition: 'background-color 120ms ease',
        // Explicit striping rather than `:nth-of-type`, which would restripe
        // on every scroll once rows are virtualized.
        ...(isStriped && { bgcolor: 'rgba(255, 255, 255, 0.022)' }),
        ...(isLarge && {
          bgcolor: 'rgba(245, 158, 11, 0.1)',
          boxShadow: 'inset 2px 0 0 var(--mui-palette-warning-main)',
        }),
      }}
    >
      <TableCell
        sx={{
          fontVariantNumeric: 'tabular-nums',
          color: 'text.secondary',
          // Keeps the timestamp visible when a narrow viewport scrolls the
          // table horizontally — without it, the one column that identifies
          // a row is the first to disappear.
          position: 'sticky',
          left: 0,
          zIndex: 1,
          bgcolor: stickyBackground,
        }}
      >
        {timeFormatter.format(new Date(trade.event_time))}
      </TableCell>
      <TableCell
        align="right"
        sx={{ color: SIDE_COLOR[side], fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
      >
        {formatDecimal(trade.price)}
      </TableCell>
      <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {formatDecimal(trade.size)}
      </TableCell>
      <TableCell>
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Box component="span" sx={{ color: SIDE_COLOR[side], fontWeight: 600 }}>
            {SIDE_LABEL[side]}
          </Box>
          {isLarge ? (
            <Box
              component="span"
              sx={{
                fontSize: '0.65rem',
                fontWeight: 700,
                color: 'warning.main',
                border: '1px solid',
                borderColor: 'warning.main',
                borderRadius: 0.5,
                px: 0.5,
                lineHeight: 1.5,
              }}
            >
              Large
            </Box>
          ) : null}
        </Stack>
      </TableCell>
      {showTradeValue ? (
        <TableCell
          align="right"
          sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: isLarge ? 700 : 400 }}
        >
          {formatDecimal(String(value))}
        </TableCell>
      ) : null}
    </TableRow>
  );
}

const TradeTapeRow = memo(TradeTapeRowInner);

/** A zero-content row that reserves the height of the rows virtualization skipped. */
function Spacer({ height, columns }: { height: number; columns: number }) {
  if (height <= 0) {
    return null;
  }
  // `aria-hidden` keeps spacers out of the accessibility tree entirely, so
  // assistive tech — and `getAllByRole('row')` — see only real trades.
  return (
    <TableRow aria-hidden sx={{ height }}>
      <TableCell colSpan={columns} sx={{ p: 0, border: 0 }} />
    </TableRow>
  );
}

/**
 * Newest-first trade tape. `trades` is capped upstream by `useMarketStream`'s
 * `maxTrades` option so neither the buffer nor this table grows without
 * bound on a busy market.
 *
 * Rows are tinted by aggressor side — a buy means the taker lifted the
 * offer. This is the exchange's own classification, not one inferred from
 * price movement. A newly-arrived row plays a brief fade/highlight-in
 * animation (`@keyframes tradeRowEnter`, applied only on mount via the
 * stable per-trade key above), zebra striping keeps long runs readable, the
 * timestamp column stays pinned during horizontal scroll, and a trade at or
 * above `largeTradeThreshold` gets a persistent tint plus a "Large" chip.
 *
 * With `virtualize` on and more than `VIRTUALIZE_THRESHOLD` rows, only the
 * rows near the viewport are rendered; the rest are replaced by two spacer
 * rows that reserve their exact height, so the scrollbar behaves normally.
 */
function TradeTapeInner({
  trades,
  isConnecting,
  maxTrades,
  showTradeValue = false,
  largeTradeThreshold,
  virtualize = false,
  action,
  valueColumnInfo,
}: TradeTapeProps) {
  const keys = useTradeKeys(trades);
  const [scrollTop, setScrollTop] = useState(0);

  const handleScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

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

  const columns = showTradeValue ? 5 : 4;
  const isVirtualized = virtualize && trades.length > VIRTUALIZE_THRESHOLD;
  const windowSize = Math.ceil(BODY_HEIGHT / ROW_HEIGHT) + OVERSCAN * 2;
  const startIndex = isVirtualized ? Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN) : 0;
  const endIndex = isVirtualized ? Math.min(trades.length, startIndex + windowSize) : trades.length;
  const visible = isVirtualized ? trades.slice(startIndex, endIndex) : trades;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        useFlexGap
        sx={{ mb: 1 }}
      >
        <Stack direction="row" spacing={1} alignItems="baseline">
          <Typography variant="subtitle2" component="h2" sx={{ fontWeight: 700 }}>
            Trade Tape
          </Typography>
          <Typography variant="caption" color="text.secondary">
            newest first · last {maxTrades}
            {isVirtualized ? ' · virtualized' : ''}
          </Typography>
        </Stack>
        {action}
      </Stack>
      {trades.length === 0 ? (
        <Alert severity="info" role="status">
          Connected, but no trades have printed yet. Quiet markets can go minutes between trades.
        </Alert>
      ) : (
        <TableContainer sx={{ maxHeight: BODY_HEIGHT }} onScroll={handleScroll}>
          <Table
            size="small"
            stickyHeader
            aria-label="Recent trades"
            aria-rowcount={trades.length}
            sx={{
              '@keyframes tradeRowEnter': {
                from: { backgroundColor: 'rgba(59, 130, 246, 0.28)' },
                to: { backgroundColor: 'transparent' },
              },
              '& td, & th': { borderColor: 'divider' },
            }}
          >
            <TableHead>
              <TableRow>
                <TableCell
                  scope="col"
                  sx={{ position: 'sticky', left: 0, zIndex: 3, fontWeight: 700 }}
                >
                  Time
                </TableCell>
                <TableCell scope="col" align="right" sx={{ fontWeight: 700 }}>
                  Price
                </TableCell>
                <TableCell scope="col" align="right" sx={{ fontWeight: 700 }}>
                  Quantity
                </TableCell>
                <TableCell scope="col" sx={{ fontWeight: 700 }}>
                  Side
                </TableCell>
                {showTradeValue ? (
                  <TableCell scope="col" align="right" sx={{ fontWeight: 700 }}>
                    <Stack
                      direction="row"
                      spacing={0.25}
                      alignItems="center"
                      justifyContent="flex-end"
                    >
                      <span>Trade Value</span>
                      {valueColumnInfo}
                    </Stack>
                  </TableCell>
                ) : null}
              </TableRow>
            </TableHead>
            <TableBody>
              <Spacer height={startIndex * ROW_HEIGHT} columns={columns} />
              {visible.map((trade, index) => {
                const key = keys[startIndex + index] ?? 0;
                const value = tradeValue(trade);
                return (
                  <TradeTapeRow
                    key={key}
                    trade={trade}
                    isLarge={
                      largeTradeThreshold !== undefined &&
                      Number.isFinite(value) &&
                      value >= largeTradeThreshold
                    }
                    isStriped={key % 2 === 1}
                    showTradeValue={showTradeValue}
                  />
                );
              })}
              <Spacer height={(trades.length - endIndex) * ROW_HEIGHT} columns={columns} />
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Paper>
  );
}

export const TradeTape = memo(TradeTapeInner);
