'use client';

import { useQuery } from '@tanstack/react-query';
import { fetchNewsArticles, type NewsArticleListParams } from '@/lib/api/news';

/** A page of real news articles, filterable by tracked symbol and/or a
 * published_at date range — the `/news` page's own data source. */
export function useNewsArticles(params: NewsArticleListParams = {}) {
  return useQuery({
    queryKey: ['news', 'articles', params],
    queryFn: () => fetchNewsArticles(params),
    staleTime: 60_000,
  });
}
