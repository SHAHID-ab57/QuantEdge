import type { LiveTradeData } from '@/types/api/market-stream';

/**
 * CSV export for the trade tape. Deliberately exports exactly the rows the
 * user can currently see — the same side/minimum-size filters and row cap
 * that are applied to the table — rather than the full session. Exporting
 * something other than what is on screen would be a surprise, and the full
 * session's trades are not retained anywhere client-side to export in the
 * first place (only O(1) accumulators and a bounded rolling window are —
 * see `engine/trade-analytics-engine.ts`).
 */
function escapeCsv(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

function csvLine(values: (string | number)[]): string {
  return values.map((value) => escapeCsv(String(value))).join(',');
}

export interface TapeExportContext {
  symbol: string;
  sideFilter: string;
  minSize: number;
}

/**
 * Leads with a short metadata block naming the symbol and the filters in
 * effect, matching the History page's export convention — a bare table of
 * numbers with no record of what produced it is not reproducible research.
 */
export function tradesToCsv(trades: readonly LiveTradeData[], context: TapeExportContext): string {
  const meta: [string, string][] = [
    ['Market', context.symbol],
    ['Exported at', new Date().toISOString()],
    ['Side filter', context.sideFilter],
    ['Minimum size', context.minSize > 0 ? String(context.minSize) : 'none'],
    ['Rows exported', String(trades.length)],
    ['Scope', 'Visible trade tape rows only (not the full session)'],
  ];
  const header = csvLine(['Key', 'Value']);
  const metadata = meta.map(([key, value]) => csvLine([key, value]));
  const dataHeader = csvLine(['Event Time', 'Price', 'Quantity', 'Side', 'Trade Value']);
  const rows = trades.map((trade) => {
    const value = Number(trade.price) * Number(trade.size);
    return csvLine([
      trade.event_time,
      trade.price,
      trade.size,
      trade.side,
      Number.isFinite(value) ? String(value) : '',
    ]);
  });
  return [header, ...metadata, '', dataHeader, ...rows].join('\n');
}

export function tapeExportFileName(symbol: string): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return `${symbol.replace(/[^a-zA-Z0-9_-]/g, '-')}-trade-tape-${stamp}.csv`;
}
