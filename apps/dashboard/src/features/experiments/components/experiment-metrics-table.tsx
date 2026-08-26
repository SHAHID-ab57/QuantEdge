'use client';

import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import type { Metric } from '@/types/api/experiments';

export interface ExperimentMetricsTableProps {
  metrics: Metric[];
  onAdd: (metric: { name: string; value: number; unit: string | null }) => void;
  onDelete: (metricId: string) => void;
  adding?: boolean;
}

/**
 * Every evaluation metric recorded against this experiment — the Metrics
 * entity's own table, plus a small inline form to record another. There is
 * no training engine to produce these automatically yet (see `AI.md` §
 * "Experiment Management"), so a researcher records them by hand from
 * whatever they measured elsewhere.
 */
export function ExperimentMetricsTable({
  metrics,
  onAdd,
  onDelete,
  adding = false,
}: ExperimentMetricsTableProps) {
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState('');

  const canAdd =
    name.trim().length > 0 && value.trim().length > 0 && Number.isFinite(Number(value));

  const handleAdd = () => {
    onAdd({ name: name.trim(), value: Number(value), unit: unit.trim() || null });
    setName('');
    setValue('');
    setUnit('');
  };

  return (
    <Stack spacing={1.5} aria-label="Experiment metrics">
      {metrics.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No metrics recorded yet.
        </Typography>
      ) : (
        <Table size="small" aria-label="Metrics table">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell align="right">Value</TableCell>
              <TableCell>Unit</TableCell>
              <TableCell>Recorded</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {metrics.map((metric) => (
              <TableRow key={metric.id} hover>
                <TableCell>{metric.name}</TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                  {metric.value}
                </TableCell>
                <TableCell>{metric.unit ?? '—'}</TableCell>
                <TableCell>{new Date(metric.recorded_at).toLocaleString()}</TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    aria-label={`Delete metric ${metric.name}`}
                    onClick={() => onDelete(metric.id)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Metric name' } }}
          sx={{ minWidth: 140 }}
        />
        <TextField
          size="small"
          label="Value"
          type="number"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Metric value' } }}
          sx={{ minWidth: 110 }}
        />
        <TextField
          size="small"
          label="Unit"
          value={unit}
          onChange={(event) => setUnit(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Metric unit' } }}
          sx={{ minWidth: 110 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={handleAdd}
          disabled={!canAdd || adding}
        >
          {adding ? 'Adding…' : 'Add Metric'}
        </Button>
      </Stack>
    </Stack>
  );
}
