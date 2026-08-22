'use client';

import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useTheme, alpha } from '@mui/material/styles';
import { memo, useMemo } from 'react';
import { formatDecimal, formatNumber } from '@/features/history/lib/format';
import { formatPrice } from '@/features/markets/lib/format';
import type { DepthRow } from '../lib/order-book-depth';

export type OrderBookSide = 'bids' | 'asks';

export interface OrderBookTableProps {
  side: OrderBookSide;
  rows: DepthRow[];
}

export interface OrderBookRowProps {
  row: DepthRow;
  isBids: boolean;
  barColor: string;
  priceColor: string;
}

/**
 * One price level. Split out from `OrderBookTable` specifically so it can
 * be memoized *by value* — `computeDepthRows` (`lib/order-book-depth.ts`)
 * returns a brand-new `DepthRow` object for every row on every update
 * (it's a live order book; the data really did change), so a plain
 * `React.memo` with its default reference comparison would never bail out.
 * The custom comparator below compares the four numbers that actually
 * reach the DOM instead, so a row whose price/size/total/depthRatio are
 * unchanged between two updates skips re-rendering (and re-diffing its
 * three cells) even though its parent table re-rendered and its containing
 * array is a new reference.
 */
function OrderBookRowInner({ row, isBids, barColor, priceColor }: OrderBookRowProps) {
  const barPercent = row.depthRatio * 100;
  return (
    <TableRow
      hover
      sx={{
        backgroundImage: `linear-gradient(to ${isBids ? 'left' : 'right'}, ${barColor} ${barPercent}%, transparent ${barPercent}%)`,
        backgroundRepeat: 'no-repeat',
      }}
    >
      {isBids ? (
        <>
          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatNumber(row.total)}
          </TableCell>
          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatDecimal(String(row.size))}
          </TableCell>
          <TableCell
            align="right"
            sx={{ color: priceColor, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
          >
            {formatPrice(String(row.price))}
          </TableCell>
        </>
      ) : (
        <>
          <TableCell
            align="right"
            sx={{ color: priceColor, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}
          >
            {formatPrice(String(row.price))}
          </TableCell>
          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatDecimal(String(row.size))}
          </TableCell>
          <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatNumber(row.total)}
          </TableCell>
        </>
      )}
    </TableRow>
  );
}

/**
 * The equality check behind `OrderBookRow`'s memoization — exported so it
 * can be unit-tested directly. `React.memo`'s skip-the-render-when-equal
 * behavior is a framework guarantee once this comparator is correct, so
 * testing this function *is* testing "unchanged rows never re-render" —
 * a full-DOM test couldn't distinguish "the row's render function was
 * skipped" from "it re-ran and produced identical output" (React reuses
 * DOM nodes in both cases), so the comparator is the right, precise unit
 * to verify.
 */
export function orderBookRowPropsAreEqual(
  previous: OrderBookRowProps,
  next: OrderBookRowProps,
): boolean {
  return (
    previous.isBids === next.isBids &&
    previous.barColor === next.barColor &&
    previous.priceColor === next.priceColor &&
    previous.row.price === next.row.price &&
    previous.row.size === next.row.size &&
    previous.row.total === next.row.total &&
    previous.row.depthRatio === next.row.depthRatio
  );
}

const OrderBookRow = memo(OrderBookRowInner, orderBookRowPropsAreEqual);

/**
 * One side of the book. Bids and asks are two instances of the same
 * component (mirrored by `side`) rather than two near-duplicate
 * components — sort order, color, and which edge the depth bar grows from
 * are the only differences, and all three are already fully determined by
 * `side`.
 *
 * The depth bar is a plain CSS `background-image` gradient on the row, not
 * a chart-library element or an extra absolutely-positioned node — no
 * imperative canvas work, no extra DOM per row. `React.memo` here plus the
 * caller passing a memoized `rows` array (see `order-book-page.tsx`) skips
 * this component's own re-render when neither `side` nor the row data
 * changed at all; `OrderBookRow`'s own value-based memo (above) is what
 * additionally keeps *individual unchanged rows* from re-rendering even
 * when the table itself does re-render because some other row moved.
 */
function OrderBookTableInner({ side, rows }: OrderBookTableProps) {
  const theme = useTheme();
  const isBids = side === 'bids';
  const label = isBids ? 'Bids' : 'Asks';

  // Recomputed only when the theme or side actually changes, not on every
  // streamed update — `alpha()` isn't expensive, but there's no reason to
  // redo it on every one of possibly dozens of updates per second either.
  const barColor = useMemo(
    () => alpha(isBids ? theme.palette.success.main : theme.palette.error.main, 0.18),
    [isBids, theme.palette.success.main, theme.palette.error.main],
  );
  const priceColor = isBids ? 'success.main' : 'error.main';

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5, textAlign: isBids ? 'right' : 'left' }}>
        {label}
      </Typography>
      <TableContainer sx={{ maxHeight: 520 }}>
        <Table size="small" stickyHeader aria-label={`Order book ${label.toLowerCase()}`}>
          <TableHead>
            <TableRow>
              {isBids ? (
                <>
                  <TableCell align="right">Total</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Price</TableCell>
                </>
              ) : (
                <>
                  <TableCell align="left">Price</TableCell>
                  <TableCell align="right">Size</TableCell>
                  <TableCell align="right">Total</TableCell>
                </>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <OrderBookRow
                // Price is each level's natural, stable identity — the
                // same price always means the same row across updates,
                // even though `row` itself is a new object every time.
                key={row.price}
                row={row}
                isBids={isBids}
                barColor={barColor}
                priceColor={priceColor}
              />
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

export const OrderBookTable = memo(OrderBookTableInner);
