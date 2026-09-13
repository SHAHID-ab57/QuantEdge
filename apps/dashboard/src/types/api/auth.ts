import { z } from 'zod';

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number().int().nonnegative(),
});

export type TokenResponse = z.infer<typeof TokenResponseSchema>;

export const CurrentUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  created_at: z.string(),
});

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
