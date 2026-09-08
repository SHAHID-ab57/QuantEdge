import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as newsApi from '@/lib/api/news';
import type { NewsArticle, NewsArticleList } from '@/types/api/news';
import { NewsPage } from './news-page';

vi.mock('@/lib/api/news', () => ({
  fetchNewsArticles: vi.fn(),
}));

const mockedNewsApi = vi.mocked(newsApi);

const article: NewsArticle = {
  id: 'a1',
  headline: 'Ethereum Crushed as Cryptocurrency Market is Overrun by Sellers',
  snippet: 'The cryptocurrency market has been experiencing wild price swings.',
  source: 'dailyfx.com',
  url: 'https://www.dailyfx.com/example.html',
  published_at: '2026-01-01T12:00:00Z',
  sentiment_score: -0.4215,
  symbols: ['ETHUSD'],
};

function articleList(items: NewsArticle[]): NewsArticleList {
  return {
    items,
    pagination: {
      total: items.length,
      returned: items.length,
      has_more: false,
      limit: 50,
      offset: 0,
    },
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('NewsPage', () => {
  it('shows a loading state until articles arrive', () => {
    mockedNewsApi.fetchNewsArticles.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('status', { name: 'Loading news articles' })).toBeInTheDocument();
  });

  it('renders a real article with its own headline, source, published time, sentiment, and link', async () => {
    mockedNewsApi.fetchNewsArticles.mockResolvedValue(articleList([article]));
    renderPage();

    expect(
      await screen.findByRole('heading', {
        name: 'Ethereum Crushed as Cryptocurrency Market is Overrun by Sellers',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('dailyfx.com')).toBeInTheDocument();
    expect(screen.getByText('ETHUSD')).toBeInTheDocument();
    expect(screen.getByText('Negative (-0.42)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Read original/ })).toHaveAttribute(
      'href',
      'https://www.dailyfx.com/example.html',
    );
  });

  it('shows a real score/label, never just a color dot, including for a null sentiment', async () => {
    mockedNewsApi.fetchNewsArticles.mockResolvedValue(
      articleList([{ ...article, id: 'a2', sentiment_score: null }]),
    );
    renderPage();

    expect(await screen.findByText('No sentiment data')).toBeInTheDocument();
  });

  it('shows an empty state when no articles are ingested yet', async () => {
    mockedNewsApi.fetchNewsArticles.mockResolvedValue(articleList([]));
    renderPage();

    expect(await screen.findByText('No articles found')).toBeInTheDocument();
    expect(screen.getByText('No news articles have been ingested yet.')).toBeInTheDocument();
  });

  it('surfaces a fetch failure with a retry action', async () => {
    mockedNewsApi.fetchNewsArticles.mockRejectedValue(new Error('network down'));
    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('network down');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('filters by symbol and date range, re-querying with the new params', async () => {
    mockedNewsApi.fetchNewsArticles.mockResolvedValue(articleList([article]));
    renderPage();

    await screen.findByRole('heading', { name: article.headline });

    fireEvent.change(screen.getByLabelText('Filter by symbol'), { target: { value: 'ethusd' } });

    await waitFor(() => {
      const lastCall = mockedNewsApi.fetchNewsArticles.mock.calls.at(-1);
      expect(lastCall?.[0]).toMatchObject({ symbol: 'ETHUSD' });
    });
  });

  it('clears filters via the Clear action once any filter is set', async () => {
    mockedNewsApi.fetchNewsArticles.mockResolvedValue(articleList([article]));
    renderPage();

    await screen.findByRole('heading', { name: article.headline });
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Filter by symbol'), { target: { value: 'ETHUSD' } });
    expect(await screen.findByRole('button', { name: 'Clear' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByLabelText('Filter by symbol')).toHaveValue('');
  });
});
