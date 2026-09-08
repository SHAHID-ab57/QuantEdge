'use client';

import Chip from '@mui/material/Chip';
import { classifySentiment, formatSentiment, type SentimentLabel } from '../lib/sentiment-label';

export interface SentimentChipProps {
  score: number | null;
}

const CHIP_COLOR: Record<SentimentLabel, 'success' | 'error' | 'default'> = {
  positive: 'success',
  neutral: 'default',
  negative: 'error',
  unknown: 'default',
};

/** An article's own sentiment as an actual score/label, not just a color
 * dot — e.g. "Positive (0.42)" — per this page's own explicit design
 * requirement. */
export function SentimentChip({ score }: SentimentChipProps) {
  return (
    <Chip
      label={formatSentiment(score)}
      color={CHIP_COLOR[classifySentiment(score)]}
      size="small"
      variant={score === null ? 'outlined' : 'filled'}
    />
  );
}
