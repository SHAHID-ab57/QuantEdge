'use client';

import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type { MetricMetadata } from '@/types/api/evaluation';

export interface MetricCatalogPanelProps {
  metrics: MetricMetadata[];
}

/**
 * Every registered metric, classification and regression alike — the same
 * catalogue `GET /evaluation/metrics` serves, shown here as a reference so
 * "what does this engine compare, and can I add another metric" has a
 * visible answer on the page itself rather than only in the docs. A new
 * metric (a `Metric` subclass decorated with `@register`,
 * `app/evaluation/metrics/`) appears here automatically — this table adds
 * no per-metric code.
 */
export function MetricCatalogPanel({ metrics }: MetricCatalogPanelProps) {
  const classification = metrics.filter((m) => m.category === 'classification');
  const regression = metrics.filter((m) => m.category === 'regression');

  return (
    <Stack spacing={2}>
      {[
        { title: 'Classification metrics', rows: classification },
        { title: 'Regression metrics', rows: regression },
      ].map((group) => (
        <Stack key={group.title} spacing={0.5}>
          <Typography variant="caption" sx={{ fontWeight: 700 }}>
            {group.title}
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Metric</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Description</TableCell>
                <TableCell align="center">Direction</TableCell>
                <TableCell align="center">Requires probabilities</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {group.rows.map((metric) => (
                <TableRow key={metric.name}>
                  <TableCell>
                    <Chip size="small" label={metric.label} />
                  </TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" label={metric.category} />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {metric.description}
                    </Typography>
                  </TableCell>
                  <TableCell align="center">
                    <Stack
                      direction="row"
                      spacing={0.5}
                      alignItems="center"
                      justifyContent="center"
                    >
                      {metric.higher_is_better ? (
                        <ArrowUpwardIcon fontSize="small" color="success" />
                      ) : (
                        <ArrowDownwardIcon fontSize="small" color="success" />
                      )}
                      <Typography variant="caption">
                        {metric.higher_is_better ? 'Higher is better' : 'Lower is better'}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="center">
                    {metric.requires_probabilities ? 'Yes' : 'No'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Stack>
      ))}
    </Stack>
  );
}
