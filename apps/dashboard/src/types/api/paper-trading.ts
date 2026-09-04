import { z } from 'zod';

/**
 * Wire schemas for the Paper Trading API (see
 * `services/api/app/api/v1/endpoints/paper_trading.py` /
 * `services/api/app/schemas/paper_trading.py`). Every response is
 * validated against these before the app trusts it, matching every other
 * domain's own convention — every `Decimal`-backed field is a JSON string
 * on the wire (`z.string()`), the same convention `market.ts`'s own
 * candle `open`/`high`/`low`/`close`/`volume` already established.
 */

export const PAPER_ORDER_SIDES = ['buy', 'sell'] as const;
export const PaperOrderSideSchema = z.enum(PAPER_ORDER_SIDES);
export type PaperOrderSide = z.infer<typeof PaperOrderSideSchema>;

export const PAPER_PRICE_SOURCES = ['ticker', 'trade', 'candle_close'] as const;
export const PaperPriceSourceSchema = z.enum(PAPER_PRICE_SOURCES);
export type PaperPriceSource = z.infer<typeof PaperPriceSourceSchema>;

export const PaperAccountSchema = z.object({
  id: z.string(),
  name: z.string().nullable(),
  starting_balance: z.string(),
  balance: z.string(),
  realized_pnl: z.string(),
  max_position_size_pct: z.string(),
  max_exposure_pct: z.string(),
  max_drawdown_pct: z.string(),
  peak_balance: z.string(),
  trading_halted: z.boolean(),
  created_at: z.string().datetime(),
});

export type PaperAccount = z.infer<typeof PaperAccountSchema>;

export const PaperAccountListResponseSchema = z.object({
  accounts: z.array(PaperAccountSchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type PaperAccountListResponse = z.infer<typeof PaperAccountListResponseSchema>;

export const PaperOrderSchema = z.object({
  id: z.string(),
  account_id: z.string(),
  symbol: z.string(),
  side: PaperOrderSideSchema,
  quantity: z.string(),
  raw_price: z.string(),
  fill_price: z.string(),
  fill_time: z.string().datetime(),
  price_source: PaperPriceSourceSchema,
  price_observed_at: z.string().datetime(),
  is_stale_price: z.boolean(),
  slippage_applied: z.string(),
  fee_applied: z.string(),
  notional: z.string(),
  realized_pnl: z.string().nullable(),
  created_at: z.string().datetime(),
});

export type PaperOrder = z.infer<typeof PaperOrderSchema>;

export const PaperOrderListResponseSchema = z.object({
  orders: z.array(PaperOrderSchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type PaperOrderListResponse = z.infer<typeof PaperOrderListResponseSchema>;

export const PaperPositionSchema = z.object({
  symbol: z.string(),
  quantity: z.string(),
  average_entry_price: z.string(),
  current_price: z.string(),
  price_source: PaperPriceSourceSchema,
  unrealized_pnl: z.string(),
});

export type PaperPosition = z.infer<typeof PaperPositionSchema>;

export const PaperPositionListResponseSchema = z.object({
  positions: z.array(PaperPositionSchema),
});

export type PaperPositionListResponse = z.infer<typeof PaperPositionListResponseSchema>;

export const PortfolioSummarySchema = z.object({
  account_id: z.string(),
  balance: z.string(),
  realized_pnl: z.string(),
  unrealized_pnl: z.string(),
  total_equity: z.string(),
  open_position_count: z.number().int().nonnegative(),
});

export type PortfolioSummary = z.infer<typeof PortfolioSummarySchema>;

export const RiskSummarySchema = z.object({
  account_id: z.string(),
  balance: z.string(),
  peak_balance: z.string(),
  current_exposure_pct: z.string(),
  max_exposure_pct: z.string(),
  exposure_headroom_pct: z.string(),
  current_drawdown_pct: z.string(),
  max_drawdown_pct: z.string(),
  drawdown_headroom_pct: z.string(),
  max_position_size_pct: z.string(),
  trading_halted: z.boolean(),
});

export type RiskSummary = z.infer<typeof RiskSummarySchema>;
