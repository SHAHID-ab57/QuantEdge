import { apiClient } from './client';
import {
  PaperAccountListResponseSchema,
  PaperAccountSchema,
  PaperOrderListResponseSchema,
  PaperOrderSchema,
  PaperPositionListResponseSchema,
  PaperPositionSchema,
  PortfolioSummarySchema,
  RiskSummarySchema,
  type PaperAccount,
  type PaperAccountListResponse,
  type PaperOrder,
  type PaperOrderListResponse,
  type PaperOrderSide,
  type PaperPosition,
  type PaperPositionListResponse,
  type PortfolioSummary,
  type RiskSummary,
} from '@/types/api/paper-trading';

export interface PaperAccountCreateBody {
  name?: string;
  starting_balance: string;
}

/** Open a new virtual trading account. */
export async function createPaperAccount(body: PaperAccountCreateBody): Promise<PaperAccount> {
  const { data } = await apiClient.post('/api/v1/paper-trading/accounts', body);
  return PaperAccountSchema.parse(data);
}

/** Reopen one paper trading account. */
export async function fetchPaperAccount(accountId: string): Promise<PaperAccount> {
  const { data } = await apiClient.get(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}`,
  );
  return PaperAccountSchema.parse(data);
}

export interface PaperAccountListParams {
  limit?: number;
  offset?: number;
}

/** Every paper trading account this platform has recorded. */
export async function fetchPaperAccounts(
  params: PaperAccountListParams = {},
): Promise<PaperAccountListResponse> {
  const { data } = await apiClient.get('/api/v1/paper-trading/accounts', { params });
  return PaperAccountListResponseSchema.parse(data);
}

export interface PaperOrderBody {
  symbol: string;
  side: PaperOrderSide;
  quantity: string;
  /** Buy only — sets the resulting position's stop-loss/take-profit. */
  stop_loss_price?: string;
  take_profit_price?: string;
}

/** Place and fill one market order for an account. */
export async function placePaperOrder(
  accountId: string,
  body: PaperOrderBody,
): Promise<PaperOrder> {
  const { data } = await apiClient.post(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/orders`,
    body,
  );
  return PaperOrderSchema.parse(data);
}

export interface PaperOrderListParams {
  sort?: 'symbol' | 'side' | 'fill_time' | 'created_at';
  dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

/** One account's own order history. */
export async function fetchPaperOrders(
  accountId: string,
  params: PaperOrderListParams = {},
): Promise<PaperOrderListResponse> {
  const { data } = await apiClient.get(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/orders`,
    { params },
  );
  return PaperOrderListResponseSchema.parse(data);
}

/** An account's currently-open positions, each marked to a live price. */
export async function fetchPaperPositions(accountId: string): Promise<PaperPositionListResponse> {
  const { data } = await apiClient.get(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/positions`,
  );
  return PaperPositionListResponseSchema.parse(data);
}

/** An account's own balance, realized PnL, and live unrealized PnL. */
export async function fetchPaperPortfolioSummary(accountId: string): Promise<PortfolioSummary> {
  const { data } = await apiClient.get(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/summary`,
  );
  return PortfolioSummarySchema.parse(data);
}

/** An account's own current exposure %, drawdown %, distance to each
 * limit, and halted status. */
export async function fetchPaperTradingRisk(accountId: string): Promise<RiskSummary> {
  const { data } = await apiClient.get(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/risk`,
  );
  return RiskSummarySchema.parse(data);
}

/** Explicitly clear a drawdown halt — the only way it ever clears. */
export async function resumePaperTrading(accountId: string): Promise<PaperAccount> {
  const { data } = await apiClient.post(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/resume-trading`,
  );
  return PaperAccountSchema.parse(data);
}

export interface PositionThresholdsUpdateBody {
  /** Omit a field to leave it unchanged; pass `null` to clear it. */
  stop_loss_price?: string | null;
  take_profit_price?: string | null;
}

/** Set, update, or clear one position's stop-loss/take-profit. */
export async function updatePositionThresholds(
  accountId: string,
  symbol: string,
  body: PositionThresholdsUpdateBody,
): Promise<PaperPosition> {
  const { data } = await apiClient.patch(
    `/api/v1/paper-trading/accounts/${encodeURIComponent(accountId)}/positions/${encodeURIComponent(symbol)}`,
    body,
  );
  return PaperPositionSchema.parse(data);
}
