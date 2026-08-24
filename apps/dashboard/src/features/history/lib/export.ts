import { csvLine, sanitizeFilenamePart } from '@/lib/csv';
import type { Candle, CandlePage, CandleQuality, CandleStatistics } from '@/types/api/market';
import type { HistoryQuery } from '../hooks/use-history-data';
import { formatNumber } from './format';

export { sanitizeFilenamePart };

export interface ExportEnvelope {
  exported_at: string;
  market: string;
  timeframe: string;
  filters: {
    start: string | null;
    end: string | null;
    limit: number;
    sort: string;
    dir: string;
  };
  statistics: CandleStatistics;
  quality: CandleQuality;
  candles: Candle[];
}

export function buildEnvelope(
  query: HistoryQuery,
  candles: Candle[],
  page: CandlePage,
): ExportEnvelope {
  return {
    exported_at: new Date().toISOString(),
    market: query.symbol,
    timeframe: query.timeframe,
    filters: {
      start: query.start,
      end: query.end,
      limit: query.limit,
      sort: query.sort,
      dir: query.dir,
    },
    statistics: page.statistics,
    quality: page.quality,
    candles,
  };
}

export function envelopeToCsv(envelope: ExportEnvelope): string {
  const statistics = envelope.statistics;
  const quality = envelope.quality;
  const meta: [string, string | number | null][] = [
    ['Market', envelope.market],
    ['Timeframe', envelope.timeframe],
    ['Export time', envelope.exported_at],
    ['Start', envelope.filters.start ?? 'all history'],
    ['End', envelope.filters.end ?? 'all history'],
    ['Sort', `${envelope.filters.sort} ${envelope.filters.dir}`],
    ['Total candles', formatNumber(statistics.total_candles)],
    ['Expected candles', formatNumber(statistics.expected_candles)],
    ['Missing candles', formatNumber(statistics.missing_candles)],
    ['Completeness', statistics.completeness !== null ? `${statistics.completeness}%` : '—'],
    ['Freshness score', `${quality.freshness_score} of 100`],
    ['Overall quality', `${quality.overall_quality_score} of 100`],
    ['Duplicate buckets', formatNumber(quality.duplicate_candles)],
    ['Out-of-order candles', formatNumber(quality.out_of_order_candles)],
    ['Invalid OHLC candles', formatNumber(quality.invalid_ohlc_candles)],
  ];
  const header = csvLine(['Key', 'Value']);
  const metadata = meta.map(([key, value]) => csvLine([key, value ?? '—']));
  const dataHeader = csvLine(['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume']);
  const rows = envelope.candles.map((candle) =>
    csvLine([candle.open_time, candle.open, candle.high, candle.low, candle.close, candle.volume]),
  );
  return [header, ...metadata, '', dataHeader, ...rows].join('\n');
}

export function exportFileName(query: HistoryQuery, extension: 'csv' | 'json'): string {
  const start = sanitizeFilenamePart(query.start?.slice(0, 10) ?? null);
  const end = sanitizeFilenamePart(query.end?.slice(0, 10) ?? null);
  return `${query.symbol}-${query.timeframe}-${start}-${end}.${extension}`;
}
