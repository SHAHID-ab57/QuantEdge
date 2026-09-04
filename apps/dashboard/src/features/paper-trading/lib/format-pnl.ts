/** Formats a signed dollar amount with the sign *before* the dollar sign
 * (`-$50.00`, `+$995.00`, `$0.00`) — the standard financial display
 * convention, and the one place this is computed so every PnL figure on
 * this page (account summary, positions, order history) reads
 * consistently rather than each formatting it slightly differently. */
export function formatSignedCurrency(value: number): string {
  let sign = '';
  if (value > 0) sign = '+';
  if (value < 0) sign = '-';
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}
