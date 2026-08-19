import { isAxiosError } from 'axios';
import type { ApiErrorData } from '@/types';

export class ApiError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly data: unknown;
  readonly network: boolean;

  constructor(
    status: number | null,
    code: string,
    message: string,
    data: unknown = null,
    network = false,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.data = data;
    this.network = network;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (isAxiosError(error)) {
    const response = error.response;
    if (response) {
      const data = response.data as ApiErrorData | undefined;
      const detail = data?.detail;
      return new ApiError(
        response.status,
        `HTTP_${response.status}`,
        typeof detail === 'string' ? detail : error.message,
        response.data,
        false,
      );
    }
    if (error.code === 'ECONNABORTED') {
      return new ApiError(null, 'TIMEOUT', 'Request timed out', null, true);
    }
    return new ApiError(null, 'NETWORK', 'Network error', null, true);
  }
  return new ApiError(null, 'UNKNOWN', error instanceof Error ? error.message : 'Unknown error');
}
