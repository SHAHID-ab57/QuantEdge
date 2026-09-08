import { apiClient } from './client';
import { NewsArticleListSchema, type NewsArticleList } from '@/types/api/news';

export interface NewsArticleListParams {
  symbol?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}

/** A page of real news articles, newest first, optionally filtered by
 * tracked symbol and/or a published_at date range. */
export async function fetchNewsArticles(
  params: NewsArticleListParams = {},
): Promise<NewsArticleList> {
  const search = new URLSearchParams();
  if (params.symbol) search.set('symbol', params.symbol);
  if (params.start) search.set('start', params.start);
  if (params.end) search.set('end', params.end);
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  const query = search.toString();
  const { data } = await apiClient.get(
    query ? `/api/v1/news/articles?${query}` : '/api/v1/news/articles',
  );
  return NewsArticleListSchema.parse(data);
}
