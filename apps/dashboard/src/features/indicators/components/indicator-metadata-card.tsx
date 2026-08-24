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
 * response's own `IndicatorMetadata` (category, version, author,
 * complexity, warmup description — all additive fields the backend
 * publishes per indicator, never hardcoded here per indicator name), or
 * an architectural guarantee documented in `ARCHITECTURE.md`
 * (Replay/Backtesting/Feature-Engineering support is a property of the
 * engine's design — every indicator gets it, not a per-indicator flag).
 * Nothing is fabricated.
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
          label="Supported Price Sources"
          value={
            indicator.parameters
              .find((parameter) => parameter.name === 'source')
              ?.choices.join(', ') ?? 'N/A'
          }
        />
        <Fact
          label="Time Complexity"
          value={indicator.complexity}
          hint="Published by the indicator itself, not assumed by this page."
        />
        <Fact
          label="Warmup Requirement"
          value={result ? `${result.meta.warmup_candles} candles` : indicator.warmup_description}
          hint={
            result
              ? indicator.warmup_description
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
        <Fact label="Indicator Version" value={indicator.version} />
        <Fact label="Author" value={indicator.author} />
      </Stack>
    </Paper>
  );
}

export const IndicatorMetadataCard = memo(IndicatorMetadataCardInner);
