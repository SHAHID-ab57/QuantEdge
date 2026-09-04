import { apiClient } from './client';
import {
  PaperAccountListResponseSchema,
  PaperAccountSchema,
  PaperOrderListResponseSchema,
  PaperOrderSchema,
  PaperPositionListResponseSchema,
  PortfolioSummarySchema,
  RiskSummarySchema,
  type PaperAccount,
  type PaperAccountListResponse,
  type PaperOrder,
  type PaperOrderListResponse,
  type PaperOrderSide,
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
