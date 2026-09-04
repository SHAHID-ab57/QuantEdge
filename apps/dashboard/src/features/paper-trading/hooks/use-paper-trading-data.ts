'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createPaperAccount,
  fetchPaperAccount,
  fetchPaperAccounts,
  fetchPaperOrders,
  fetchPaperPortfolioSummary,
  fetchPaperPositions,
  fetchPaperTradingRisk,
  placePaperOrder,
  resumePaperTrading,
  type PaperAccountCreateBody,
  type PaperAccountListParams,
  type PaperOrderBody,
  type PaperOrderListParams,
} from '@/lib/api/paper-trading';

/** Server state for the Paper Trading page. Opening an account and placing
 * an order are both *mutations* — explicit, on-demand actions with real
 * consequences (a new account, cash actually spent) — the same posture
 * `useRunTrainingJob`/`useRunPrediction` already take for their own real
 * backend actions. Balance, positions, orders, and the summary are real
 * queries, invalidated together whenever an order is placed. */

const ACCOUNTS_KEY = ['paper-trading', 'accounts'] as const;

function accountKey(accountId: string | null) {
  return ['paper-trading', 'account', accountId] as const;
}

export function useCreatePaperAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PaperAccountCreateBody) => createPaperAccount(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ACCOUNTS_KEY }),
  });
}

export function usePaperAccounts(params: PaperAccountListParams) {
  return useQuery({
    queryKey: [...ACCOUNTS_KEY, 'list', params],
    queryFn: () => fetchPaperAccounts(params),
  });
}

export function usePaperAccount(accountId: string | null) {
  return useQuery({
    queryKey: accountKey(accountId),
    queryFn: () => fetchPaperAccount(accountId as string),
    enabled: Boolean(accountId),
  });
}

export function usePaperPortfolioSummary(accountId: string | null) {
  return useQuery({
    queryKey: [...accountKey(accountId), 'summary'],
    queryFn: () => fetchPaperPortfolioSummary(accountId as string),
    enabled: Boolean(accountId),
    // A position's own unrealized PnL depends on a live price that moves
    // on its own, unprompted by any user action — poll it, the same way
    // `useTrainingJob` polls a job still 'running'.
    refetchInterval: Boolean(accountId) && 10_000,
  });
}

export function usePaperPositions(accountId: string | null) {
  return useQuery({
    queryKey: [...accountKey(accountId), 'positions'],
    queryFn: () => fetchPaperPositions(accountId as string),
    enabled: Boolean(accountId),
    refetchInterval: Boolean(accountId) && 10_000,
  });
}

export function usePaperOrders(accountId: string | null, params: PaperOrderListParams) {
  return useQuery({
    queryKey: [...accountKey(accountId), 'orders', params],
    queryFn: () => fetchPaperOrders(accountId as string, params),
    enabled: Boolean(accountId),
  });
}

export function usePlacePaperOrder(accountId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PaperOrderBody) => placePaperOrder(accountId as string, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountKey(accountId) }),
  });
}

export function usePaperTradingRisk(accountId: string | null) {
  return useQuery({
    queryKey: [...accountKey(accountId), 'risk'],
    queryFn: () => fetchPaperTradingRisk(accountId as string),
    enabled: Boolean(accountId),
    // Exposure/drawdown depend on live prices and the account's own
    // running balance — poll it the same way the summary/positions do.
    refetchInterval: Boolean(accountId) && 10_000,
  });
}

export function useResumeTrading(accountId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => resumePaperTrading(accountId as string),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: accountKey(accountId) }),
  });
}
