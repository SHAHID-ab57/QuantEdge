import { apiClient } from './client';
import {
  CurrentUserSchema,
  TokenResponseSchema,
  type CurrentUser,
  type TokenResponse,
} from '@/types/api/auth';

export interface LoginCredentials {
  email: string;
  password: string;
}

export async function login(credentials: LoginCredentials): Promise<TokenResponse> {
  const { data } = await apiClient.post('/api/v1/auth/login', credentials);
  return TokenResponseSchema.parse(data);
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const { data } = await apiClient.get('/api/v1/auth/me');
  return CurrentUserSchema.parse(data);
}
