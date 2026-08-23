import { describe, expect, it } from 'vitest';
import type { LiveTradeData } from '@/types/api/market-stream';
import { tapeExportFileName, tradesToCsv } from './tape-export';

function trade(price: string, size: string, side = 'buy'): LiveTradeData {
  return { price, size, side, event_time: '2026-01-01T00:00:00Z' };
}

const context = { symbol: 'ETHUSD', sideFilter: 'all', minSize: 0 };

describe('tradesToCsv', () => {
  it('leads with a metadata block naming the market and the filters in effect', () => {
    const csv = tradesToCsv([trade('100', '2')], {
      symbol: 'ETHUSD',
      sideFilter: 'buy',
      minSize: 5,
    });
    expect(csv).toContain('"Market","ETHUSD"');
    expect(csv).toContain('"Side filter","buy"');
    expect(csv).toContain('"Minimum size","5"');
    expect(csv).toContain('"Rows exported","1"');
  });

  it('records that the export covers only the visible rows', () => {
    expect(tradesToCsv([], context)).toContain('Visible trade tape rows only');
  });

  it('writes one data row per trade, with a computed trade value', () => {
    const csv = tradesToCsv([trade('100', '2')], context);
    expect(csv).toContain('"Event Time","Price","Quantity","Side","Trade Value"');
    expect(csv).toContain('"2026-01-01T00:00:00Z","100","2","buy","200"');
  });

  it('leaves the trade value blank rather than writing NaN for an unparseable trade', () => {
    const csv = tradesToCsv([trade('not-a-number', '2')], context);
    expect(csv).not.toContain('NaN');
    expect(csv).toContain('"not-a-number","2","buy",""');
  });

  it('escapes embedded quotes rather than corrupting the row', () => {
    const csv = tradesToCsv([trade('100', '1', 'we"ird')], context);
    expect(csv).toContain('"we""ird"');
  });

  it('produces a header-only export for an empty tape', () => {
    const csv = tradesToCsv([], context);
    expect(csv).toContain('"Rows exported","0"');
    expect(csv.trimEnd().endsWith('"Trade Value"')).toBe(true);
  });
});

describe('tapeExportFileName', () => {
  it('includes the symbol and a filesystem-safe timestamp', () => {
    const name = tapeExportFileName('ETHUSD');
    expect(name).toMatch(/^ETHUSD-trade-tape-[\dTZ-]+\.csv$/);
  });

  it('sanitises a symbol containing characters a filesystem would reject', () => {
    expect(tapeExportFileName('ETH/USD')).toContain('ETH-USD');
  });
});
