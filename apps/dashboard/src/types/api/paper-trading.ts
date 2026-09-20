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

export const PAPER_POSITION_SIDES = ['long', 'short'] as const;
export const PaperPositionSideSchema = z.enum(PAPER_POSITION_SIDES);
export type PaperPositionSide = z.infer<typeof PaperPositionSideSchema>;

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
  max_leverage: z.string(),
  /** The highest account EQUITY ever reached (the drawdown limit's reference). */
  peak_balance: z.string(),
  trading_halted: z.boolean(),
  strategy_enabled: z.boolean(),
  strategy_training_job_id: z.string().nullable(),
  strategy_confidence_threshold_pct: z.string(),
  strategy_default_stop_loss_pct: z.string(),
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

export const PAPER_TRIGGER_REASONS = ['stop_loss', 'take_profit', 'liquidation'] as const;
export const PaperTriggerReasonSchema = z.enum(PAPER_TRIGGER_REASONS);
export type PaperTriggerReason = z.infer<typeof PaperTriggerReasonSchema>;

export const PaperOrderSchema = z.object({
  id: z.string(),
  account_id: z.string(),
  symbol: z.string(),
  side: PaperOrderSideSchema,
  /** The kind of position this order opened, added to or reduced. */
  position_side: PaperPositionSideSchema,
  leverage: z.string(),
  /** Margin posted (opening/adding) or released (reducing); forfeited on a liquidation. */
  margin_applied: z.string(),
  reduce_only: z.boolean(),
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
  trigger_reason: PaperTriggerReasonSchema.nullable(),
  /** Liquidation only: the mark price had already passed the bankruptcy price. */
  gapped_through_bankruptcy: z.boolean(),
  /** Liquidation only: `mark`, or `last_fallback` if no mark price was available. */
  trigger_price_basis: z.enum(['mark', 'last_fallback']).nullable(),
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
  side: PaperPositionSideSchema,
  /** Position size — always positive; `side` gives the direction. */
  quantity: z.string(),
  average_entry_price: z.string(),
  leverage: z.string(),
  /** Isolated margin posted against this position. */
  margin: z.string(),
  /** The mark price at which it is liquidated; null if it cannot be (a 1x long). */
  liquidation_price: z.string().nullable(),
  liquidation_distance_pct: z.string().nullable(),
  current_price: z.string(),
  price_source: PaperPriceSourceSchema,
  unrealized_pnl: z.string(),
  stop_loss_price: z.string().nullable(),
  take_profit_price: z.string().nullable(),
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
  margin_in_use: z.string(),
  total_equity: z.string(),
  total_notional: z.string(),
  effective_leverage: z.string(),
  open_position_count: z.number().int().nonnegative(),
});

export type PortfolioSummary = z.infer<typeof PortfolioSummarySchema>;

export const RiskSummarySchema = z.object({
  account_id: z.string(),
  /** Available cash (margin already posted is not included). */
  balance: z.string(),
  /** Cash + margin in use + unrealized PnL at live prices. */
  equity: z.string(),
  margin_in_use: z.string(),
  peak_balance: z.string(),
  total_notional: z.string(),
  effective_leverage: z.string(),
  current_exposure_pct: z.string(),
  max_exposure_pct: z.string(),
  exposure_headroom_pct: z.string(),
  current_drawdown_pct: z.string(),
  max_drawdown_pct: z.string(),
  drawdown_headroom_pct: z.string(),
  max_position_size_pct: z.string(),
  max_leverage: z.string(),
  trading_halted: z.boolean(),
});

export type RiskSummary = z.infer<typeof RiskSummarySchema>;

export const PAPER_STRATEGY_DECISION_ACTIONS = ['opened', 'closed', 'no_action'] as const;
export const PaperStrategyDecisionActionSchema = z.enum(PAPER_STRATEGY_DECISION_ACTIONS);
export type PaperStrategyDecisionAction = z.infer<typeof PaperStrategyDecisionActionSchema>;

export const PaperStrategyDecisionSchema = z.object({
  id: z.string(),
  account_id: z.string(),
  training_job_id: z.string().nullable(),
  symbol: z.string().nullable(),
  action: PaperStrategyDecisionActionSchema,
  reason: z.string(),
  predicted_value: z.unknown().nullable(),
  confidence: z.number().nullable(),
  confidence_threshold_pct: z.string(),
  prediction_id: z.string().nullable(),
  order_id: z.string().nullable(),
  created_at: z.string().datetime(),
});

export type PaperStrategyDecision = z.infer<typeof PaperStrategyDecisionSchema>;

export const PaperStrategyDecisionListResponseSchema = z.object({
  decisions: z.array(PaperStrategyDecisionSchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export type PaperStrategyDecisionListResponse = z.infer<
  typeof PaperStrategyDecisionListResponseSchema
>;
