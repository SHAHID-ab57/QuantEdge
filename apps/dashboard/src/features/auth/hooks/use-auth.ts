'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchCurrentUser, login, type LoginCredentials } from '@/lib/api/auth';
import { clearSessionToken, getSessionToken, setSessionToken } from '@/lib/api/session';

export const CURRENT_USER_KEY = ['auth', 'me'];

/**
 * The caller's own profile — the frontend's session check. `enabled` is
 * gated on a token actually being present in `sessionStorage` so a signed-
 * out visitor never fires a request destined to 401 (and re-trigger the
 * client's own 401 -> `/login` redirect) before `AuthGuard` has had a
 * chance to redirect them there itself.
 */
export function useCurrentUser() {
  return useQuery({
    queryKey: CURRENT_USER_KEY,
    queryFn: fetchCurrentUser,
    enabled: Boolean(getSessionToken()),
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginCredentials) => login(credentials),
    onSuccess: (token) => {
      setSessionToken(token.access_token);
      queryClient.invalidateQueries({ queryKey: CURRENT_USER_KEY });
    },
  });
}

export function logout(): void {
  clearSessionToken();
  if (typeof window !== 'undefined') {
    window.location.assign('/login');
  }
}
