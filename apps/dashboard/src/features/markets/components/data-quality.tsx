'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import RefreshIcon from '@mui/icons-material/Refresh';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import {
  QUALITY_BREAKDOWN,
  qualityBreakdown,
  qualityLabel,
  qualityRecommendations,
  type QualityInput,
  type QualityStatus,
} from '../lib/quality';

const STATUS_MARKS: Record<QualityStatus, { symbol: string; color: string }> = {
  pass: { symbol: '✔', color: 'success.main' },
  warn: { symbol: '!', color: 'warning.main' },
  fail: { symbol: '✘', color: 'error.main' },
};

function QualityMark({ status }: { status: QualityStatus }) {
  const mark = STATUS_MARKS[status];
  return (
    <Box component="span" sx={{ color: mark.color }} aria-hidden>
      {mark.symbol}{' '}
    </Box>
  );
}

function scoreColor(score: number | null): 'success' | 'warning' | 'error' {
  if (score !== null && score >= 80) {
    return 'success';
  }
  if (score !== null && score >= 50) {
    return 'warning';
  }
  return 'error';
}

export interface DataQualityProps {
  score: number | null;
  qualityInput: QualityInput | null;
  calculatedFrom: string;
  onRecalculate: () => void;
  isRefetching: boolean;
}

export function DataQuality({
  score,
  qualityInput,
  calculatedFrom,
  onRecalculate,
  isRefetching,
}: DataQualityProps) {
  const breakdown = qualityInput ? qualityBreakdown(qualityInput) : [];
  const deductions = breakdown
    .filter((item) => item.points < item.max)
    .map((item) => `${item.label} −${item.max - item.points}`);
  const recommendations = qualityInput ? qualityRecommendations(qualityInput) : [];

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="overline" color="text.secondary" component="h3">
          Data quality
        </Typography>
        <Tooltip title={QUALITY_BREAKDOWN} arrow>
          <InfoOutlinedIcon
            fontSize="small"
            color="action"
            aria-label="Data quality score explanation"
          />
        </Tooltip>
      </Stack>
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mt: 1 }}>
        <LinearProgress
          variant="determinate"
          value={score ?? 0}
          color={scoreColor(score)}
          sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
          aria-label={`Data quality score ${score}`}
        />
        <Typography variant="h6" component="p" fontWeight={700}>
          {score !== null ? `${score}/100` : '—'}
        </Typography>
        {score !== null ? (
          <Chip
            label={qualityLabel(score)}
            size="small"
            color={scoreColor(score)}
            variant="outlined"
          />
        ) : null}
        <Tooltip title="Re-fetch the underlying market data and recalculate the score" arrow>
          <Button
            size="small"
            startIcon={<RefreshIcon />}
            onClick={onRecalculate}
            disabled={isRefetching}
            aria-label="Recalculate data quality score"
          >
            Recalculate
          </Button>
        </Tooltip>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Calculated from data as of {calculatedFrom}
      </Typography>
      {deductions.length > 0 ? (
        <Typography variant="caption" color="warning.main" component="p" sx={{ display: 'block' }}>
          Deductions: {deductions.join(', ')}
        </Typography>
      ) : null}

      <Stack component="dl" spacing={0.75} sx={{ m: 0 }}>
        {breakdown.map((item) => (
          <Tooltip
            key={item.id}
            title={`${item.detail}. ${item.points} of ${item.max} points available.`}
            arrow
          >
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={1}>
              <Typography
                variant="body2"
                color="text.secondary"
                component="dt"
                sx={{ textDecoration: 'underline dotted' }}
              >
                <QualityMark status={item.status} />
                {item.label}
              </Typography>
              <Typography variant="body2" component="dd" sx={{ textAlign: 'right' }}>
                {item.points}/{item.max} · {Math.round((item.points / item.max) * 100)}%
              </Typography>
            </Stack>
          </Tooltip>
        ))}
      </Stack>

      {recommendations.length > 0 ? (
        <Box component="section" aria-label="Data quality recommendations" sx={{ mt: 1.5 }}>
          <Typography variant="overline" color="text.secondary" component="h4">
            Recommendations
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 2, pt: 0.5 }}>
            {recommendations.map((recommendation) => (
              <Typography key={recommendation} component="li" variant="body2" sx={{ py: 0.25 }}>
                {recommendation}
              </Typography>
            ))}
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
