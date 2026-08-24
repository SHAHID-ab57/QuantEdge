'use client';

import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import type { Indicator, IndicatorCalculation } from '@/types/api/indicators';

export interface IndicatorMetadataCardProps {
  indicator: Indicator;
  /** The most recent calculation for this indicator, if one has been run yet. */
  result?: IndicatorCalculation;
}

interface FactProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
}

function Fact({ label, value, hint }: FactProps) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {label}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {value}
      </Typography>
      {hint ? (
        <Typography variant="caption" color="text.disabled" sx={{ display: 'block', mt: 0.25 }}>
          {hint}
        </Typography>
      ) : null}
    </Box>
  );
}

/**
 * Engineering-facing facts about the selected indicator, distinct from the
 * research-facing `IndicatorInfoPanel` above it: not "what does this
 * measure" but "how does this fit the platform's architecture."
 *
 * Every fact here is either read straight from the catalogue/calculation
 * response, or an architectural guarantee documented in `ARCHITECTURE.md`
 * (Replay/Backtesting/Feature-Engineering support is a property of the
 * engine's design — every indicator gets it, not a per-indicator flag) —
 * nothing is fabricated. Where the API genuinely doesn't expose something
 * (a version number), that is stated plainly rather than invented.
 */
function IndicatorMetadataCardInner({ indicator, result }: IndicatorMetadataCardProps) {
  const outputType =
    indicator.outputs.length > 1
      ? `${indicator.outputs.length} series (${indicator.outputs.map((output) => output.label).join(', ')})`
      : `Single series (${indicator.outputs[0]?.label ?? indicator.name})`;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
      <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 700, mb: 1.5 }}>
        Indicator Metadata
      </Typography>
      <Stack spacing={1.5}>
        <Fact label="Category" value={indicator.category} />
        <Fact label="Output Type" value={outputType} />
        <Fact
          label="Time Complexity"
          value="O(n)"
          hint="Linear in candles analyzed — true of every indicator built on this engine's pipeline."
        />
        <Fact
          label="Warmup Requirement"
          value={result ? `${result.meta.warmup_candles} candles` : 'Depends on parameters'}
          hint={
            result
              ? 'From the most recent calculation.'
              : 'Run a calculation to see the exact candle count for the chosen parameters.'
          }
        />
        <Fact
          label="Supports Replay / Backtesting / AI Feature Engineering"
          value="Yes"
          hint="An architectural guarantee, not a per-indicator setting: every indicator on this engine takes plain candle data with no HTTP/DB dependency, so it runs unchanged in any future consumer (see ARCHITECTURE.md)."
        />
        <Fact
          label="Cache Status"
          value={result?.meta.cache_status ?? '—'}
          hint={result ? undefined : 'Available once a calculation has run.'}
        />
        <Fact
          label="Backend Engine Version"
          value="Not exposed by the API"
          hint="No versioning endpoint exists yet for the indicator engine."
        />
      </Stack>
    </Paper>
  );
}

export const IndicatorMetadataCard = memo(IndicatorMetadataCardInner);
