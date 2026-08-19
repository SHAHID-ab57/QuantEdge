import axios from 'axios';
import { env } from '@/config/env';
import { toApiError } from './errors';
import { clearSessionToken, getSessionToken } from './session';

export const apiClient = axios.create({
  baseURL: env.NEXT_PUBLIC_API_URL,
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const apiError = toApiError(error);
    if (apiError.status === 401) {
      clearSessionToken();
      if (typeof window !== 'undefined') {
        window.location.assign('/');
      }
    }
    console.warn(`[api] ${apiError.code}: ${apiError.message}`);
    return Promise.reject(apiError);
  },
);
