import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import type { ComponentStatus } from '@/types/api/system';

export const STATUS_COLOR: Record<ComponentStatus['status'], 'success' | 'warning' | 'error'> = {
  ok: 'success',
  degraded: 'warning',
  unavailable: 'error',
};

export const STATUS_LABEL: Record<ComponentStatus['status'], string> = {
  ok: 'OK',
  degraded: 'DEGRADED',
  unavailable: 'UNAVAILABLE',
};

export function StatusPill({ status }: Readonly<{ status: ComponentStatus['status'] }>) {
  return (
    <Chip
      size="small"
      color={STATUS_COLOR[status]}
      label={STATUS_LABEL[status]}
      sx={{ fontWeight: 700, letterSpacing: '0.04em' }}
    />
  );
}

export function Metric({
  label,
  value,
  emphasis = false,
}: Readonly<{ label: string; value: ReactNode; emphasis?: boolean }>) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography
        variant="caption"
        component="dt"
        color="text.secondary"
        sx={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontSize: 11 }}
      >
        {label}
      </Typography>
      <Typography
        component="dd"
        variant={emphasis ? 'h6' : 'body2'}
        sx={{
          m: 0,
          fontWeight: emphasis ? 700 : 600,
          fontVariantNumeric: 'tabular-nums',
          color: emphasis ? 'text.primary' : 'text.primary',
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}

const TONE_COLOR: Record<'default' | 'ok' | 'warn' | 'err', string> = {
  default: 'text.primary',
  ok: 'success.main',
  warn: 'warning.main',
  err: 'error.main',
};

export function MetricRow({
  label,
  value,
  tone = 'default',
}: Readonly<{
  label: string;
  value: ReactNode;
  tone?: 'default' | 'ok' | 'warn' | 'err';
}>) {
  const color = TONE_COLOR[tone];
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 2,
        py: 0.5,
      }}
    >
      <Typography variant="body2" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography
        variant="body2"
        component="dd"
        sx={{ m: 0, fontWeight: 600, color, fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </Typography>
    </Box>
  );
}
