import { z } from 'zod';

/**
 * Wire schemas for the News API (see `services/api/app/schemas/news.py`).
 * Every response is validated against these before the app trusts it,
 * matching the same convention as `connectors.ts`/`market.ts`/`features.ts`.
 */

export const NewsArticleSchema = z.object({
  id: z.string(),
  headline: z.string(),
  snippet: z.string().nullable(),
  source: z.string(),
  url: z.string(),
  published_at: z.string().datetime(),
  /** Null when none of this article's own tracked-symbol entities carried a score. */
  sentiment_score: z.number().nullable(),
  symbols: z.array(z.string()),
});

export type NewsArticle = z.infer<typeof NewsArticleSchema>;

export const NewsArticlePaginationSchema = z.object({
  total: z.number().int().nonnegative(),
  returned: z.number().int().nonnegative(),
  has_more: z.boolean(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export const NewsArticleListSchema = z.object({
  items: z.array(NewsArticleSchema),
  pagination: NewsArticlePaginationSchema,
});

export type NewsArticleList = z.infer<typeof NewsArticleListSchema>;
