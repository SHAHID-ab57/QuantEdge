'use client';

import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { memo, useMemo } from 'react';
import { StatTile } from '@/components/stat-tile';
import { formatNumber } from '@/features/markets/lib/format';
import type { IndicatorCalculation } from '@/types/api/indicators';
import { FieldInfo } from './field-info';
import { IndicatorChart } from './indicator-chart';
import { ResultSummary } from './result-summary';
import type { IndicatorKnowledge } from '../lib/indicator-knowledge';

export interface IndicatorResultsProps {
  result: IndicatorCalculation;
  knowledge: IndicatorKnowledge;
  /** Rows shown in the value table; the full series is always summarised above it. */
  maxRows?: number;
}

const DEFAULT_MAX_ROWS = 100;

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

/** Six significant digits: enough to read an indicator, without implying false precision. */
const valueFormatter = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 });

function formatValue(value: number | null): string {
  return value === null ? '—' : valueFormatter.format(value);
}

/**
 * The full results view for one calculation: a per-series summary
 * (latest/previous/change/trend/signal — see `ResultSummary`), a
 * lightweight chart of the computed series (see `IndicatorChart`), run
 * metadata, and a newest-first values table.
 *
 * Newest-first in the table because the most recent value is what a
 * researcher checks first; the underlying response is chronological
 * (indicator maths requires it) and is reversed only for display.
 */
function IndicatorResultsInner({
  result,
  knowledge,
  maxRows = DEFAULT_MAX_ROWS,
}: IndicatorResultsProps) {
  const rows = useMemo(() => {
    const indices = result.timestamps.map((_, index) => index);
    return indices
      .reverse()
      .slice(0, maxRows)
      .map((index) => ({
        index,
        timestamp: result.timestamps[index]!,
        values: result.series.map((series) => series.values[index] ?? null),
      }));
  }, [result, maxRows]);

  const truncated = result.timestamps.length > maxRows;

  return (
    <Stack spacing={2}>
      <ResultSummary series={result.series} knowledge={knowledge} />

      <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
        <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 700, mb: 1 }}>
          Chart
        </Typography>
        <IndicatorChart series={result.series} config={knowledge.chart} />
      </Paper>

      <Box
        sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 3 }, alignItems: 'center' }}
        role="status"
        aria-label="Calculation metadata"
      >
        <StatTile
          label="Candles Analyzed"
          value={formatNumber(result.meta.candles_analyzed)}
          adornment={<FieldInfo field="candlesAnalyzed" label="Candles Analyzed" />}
        />
        <StatTile
          label="Warmup Candles"
          value={formatNumber(result.meta.warmup_candles)}
          adornment={<FieldInfo field="warmupCandles" label="Warmup Candles" />}
        />
        <StatTile
          label="Calculation Time"
          value={`${result.meta.execution_time_ms.toFixed(2)} ms`}
          caption={`${result.meta.database_time_ms.toFixed(1)} ms loading candles`}
          adornment={<FieldInfo field="calculationTime" label="Calculation Time" />}
        />
        <StatTile
          label="Cache"
          value={result.meta.cache_status}
          adornment={<FieldInfo field="cacheStatus" label="Cache Status" />}
        />
      </Box>

      <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="subtitle2" component="h3" sx={{ fontWeight: 700 }}>
            Values
          </Typography>
          <FieldInfo field="resultsTable" label="Results Table" />
          <Typography variant="caption" color="text.secondary">
            newest first
            {truncated ? ` · showing ${maxRows} of ${result.timestamps.length}` : ''}
          </Typography>
        </Stack>
        <TableContainer sx={{ maxHeight: 420 }}>
          <Table size="small" stickyHeader aria-label="Indicator values">
            <TableHead>
              <TableRow>
                <TableCell scope="col" sx={{ fontWeight: 700 }}>
                  Time
                </TableCell>
                {result.series.map((series) => (
                  <TableCell key={series.name} scope="col" align="right" sx={{ fontWeight: 700 }}>
                    {series.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.timestamp} hover>
                  <TableCell sx={{ fontVariantNumeric: 'tabular-nums', color: 'text.secondary' }}>
                    {timeFormatter.format(new Date(row.timestamp))}
                  </TableCell>
                  {row.values.map((value, seriesIndex) => (
                    <TableCell
                      key={result.series[seriesIndex]!.name}
                      align="right"
                      sx={{
                        fontVariantNumeric: 'tabular-nums',
                        color: value === null ? 'text.disabled' : 'text.primary',
                      }}
                    >
                      {formatValue(value)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Stack>
  );
}

export const IndicatorResults = memo(IndicatorResultsInner);
