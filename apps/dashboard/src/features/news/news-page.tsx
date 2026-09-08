'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import ArticleIcon from '@mui/icons-material/Article';
import { useState } from 'react';
import { EmptyStateNotice } from '@/components/empty-state-notice';
import { useNewsArticles } from './hooks/use-news-articles';
import { ArticleCard } from './components/article-card';
import { NewsFilters, type NewsFiltersValue } from './components/news-filters';

const EMPTY_FILTERS: NewsFiltersValue = { symbol: '', start: '', end: '' };

function ArticleFeedSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading news articles">
      <Skeleton variant="rounded" height={110} />
      <Skeleton variant="rounded" height={110} />
      <Skeleton variant="rounded" height={110} />
    </Stack>
  );
}

/**
 * The News page (M4-E1-T7, `ARCHITECTURE.md` § "External Data Connectors"
 * → "Marketaux Connector"): a real, detailed article feed — headline,
 * source, published time, an actual sentiment score/label, and a link to
 * the original — for research to read what the `news_sentiment` daily
 * aggregate (shown on `/data-sources` as one more registry entry) is
 * actually summarizing. Deliberately its own page, not bolted onto
 * `/data-sources`: that page's entire design rests on being fully
 * generic (nothing on it names a specific source), and a rich article
 * feed would force it to special-case News.
 */
export function NewsPage() {
  const [filters, setFilters] = useState<NewsFiltersValue>(EMPTY_FILTERS);
  const articlesQuery = useNewsArticles({
    symbol: filters.symbol || undefined,
    start: filters.start ? `${filters.start}T00:00:00Z` : undefined,
    end: filters.end ? `${filters.end}T23:59:59Z` : undefined,
    limit: 50,
  });

  return (
    <Stack spacing={3}>
      <NewsFilters value={filters} onChange={setFilters} />

      {articlesQuery.isLoading && <ArticleFeedSkeleton />}

      {articlesQuery.isError && (
        <Alert
          severity="error"
          role="alert"
          action={<Button onClick={() => articlesQuery.refetch()}>Retry</Button>}
        >
          Failed to load news articles: {articlesQuery.error.message}
        </Alert>
      )}

      {articlesQuery.data && articlesQuery.data.items.length === 0 && (
        <EmptyStateNotice
          icon={<ArticleIcon fontSize="small" color="disabled" />}
          title="No articles found"
          description={
            filters.symbol || filters.start || filters.end
              ? 'No articles match these filters yet.'
              : 'No news articles have been ingested yet.'
          }
        />
      )}

      {articlesQuery.data && articlesQuery.data.items.length > 0 && (
        <Stack spacing={2}>
          {articlesQuery.data.items.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
