'use client';

import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import type { NewsArticle } from '@/types/api/news';
import { formatPublishedAt } from '../lib/format';
import { SentimentChip } from './sentiment-chip';

export interface ArticleCardProps {
  article: NewsArticle;
}

/** One real article — headline, source, published time, sentiment as an
 * actual score/label, and a link to the original, per this page's own
 * explicit design requirement (not just a daily aggregate number). */
export function ArticleCard({ article }: ArticleCardProps) {
  return (
    <Paper component="article" sx={{ p: 2 }}>
      <Stack spacing={1}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          justifyContent="space-between"
          alignItems={{ sm: 'flex-start' }}
        >
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
            {article.headline}
          </Typography>
          <SentimentChip score={article.sentiment_score} />
        </Stack>
        {article.snippet && (
          <Typography variant="body2" color="text.secondary">
            {article.snippet}
          </Typography>
        )}
        <Stack
          direction="row"
          spacing={1.5}
          alignItems="center"
          flexWrap="wrap"
          sx={{ color: 'text.secondary' }}
        >
          <Typography variant="caption">{article.source}</Typography>
          <Typography variant="caption">&bull;</Typography>
          <Typography variant="caption">{formatPublishedAt(article.published_at)}</Typography>
          {article.symbols.length > 0 && (
            <>
              <Typography variant="caption">&bull;</Typography>
              <Typography variant="caption">{article.symbols.join(', ')}</Typography>
            </>
          )}
          <Link
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            variant="caption"
            sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25, ml: 'auto' }}
          >
            Read original <OpenInNewIcon sx={{ fontSize: 14 }} />
          </Link>
        </Stack>
      </Stack>
    </Paper>
  );
}
