'use client';

import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { InfoTooltip } from '@/components/info-tooltip';
import { SplitTimeline } from './split-timeline';
import { validateSplitRatios, type SplitRatioValues } from '../lib/split-ratios';

export interface SplitConfigFormProps {
  values: SplitRatioValues;
  onChange: (values: SplitRatioValues) => void;
  /**
   * Total rows the split would apply to, if a dataset has already been
   * built at least once — lets the timeline show an estimated row count
   * per split without a second backend round-trip. Omitted before any
   * build has happened, since no row count is known yet.
   */
  estimatedTotalRows?: number;
}

const FIELDS: { key: keyof SplitRatioValues; label: string }[] = [
  { key: 'train', label: 'Train' },
  { key: 'validation', label: 'Validation' },
  { key: 'test', label: 'Test' },
];

const SPLIT_TOOLTIP_SECTIONS = [
  {
    heading: 'Chronological split',
    body: 'Train, validation, and test are contiguous slices in time order — train first, then validation, then test.',
  },
  {
    heading: 'No random shuffling',
    body: 'Rows are never reordered or shuffled before splitting.',
  },
  {
    heading: 'No look-ahead bias',
    body: 'A later split never contains a row that occurs earlier in time than an earlier split.',
  },
  {
    heading: 'Future data never leaks into training',
    body: 'Because the split is chronological, the training set can never contain a row from a time after validation or test begins.',
  },
];

/**
 * How to divide the built dataset chronologically into train, validation,
 * and test fractions. There is no shuffling anywhere in this pipeline —
 * the split is a contiguous slice in time, train first, then validation,
 * then test — so this form asks only for the three fractions, not for a
 * shuffle seed or a stratification key.
 *
 * Ratios stay backend-compatible fractions (0–1, not 0–100) — the exact
 * `split_train`/`split_validation`/`split_test` shape
 * `BuildMLDatasetParams` already sends — with a percentage shown as
 * helper text and a proportional timeline visualization underneath, so a
 * researcher reads "70%" at a glance without the wire format changing.
 * `validateSplitRatios` deliberately still allows a zero validation or
 * test ratio (only `train` must be greater than zero) — matching
 * `ChronologicalSplitter`'s own tested backend behavior
 * (`test_a_zero_ratio_split_is_allowed_for_validation_or_test`) — so this
 * form does not reject a configuration the backend explicitly supports.
 */
export function SplitConfigForm({ values, onChange, estimatedTotalRows }: SplitConfigFormProps) {
  const error = validateSplitRatios(values);

  const set = (key: keyof SplitRatioValues, raw: string) => {
    const parsed = Number(raw);
    onChange({ ...values, [key]: Number.isFinite(parsed) ? parsed : 0 });
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="flex-start">
        {FIELDS.map((field) => (
          <Stack key={field.key} direction="row" spacing={0.25} alignItems="flex-start">
            <TextField
              label={field.label}
              type="number"
              size="small"
              value={values[field.key]}
              onChange={(event) => set(field.key, event.target.value)}
              helperText={`${(values[field.key] * 100).toFixed(0)}%`}
              slotProps={{
                htmlInput: {
                  'aria-label': `${field.label} ratio`,
                  min: 0,
                  max: 1,
                  step: 0.05,
                },
              }}
              sx={{ width: 130 }}
            />
            {field.key === 'train' ? (
              <InfoTooltip label="Split ratios" sections={SPLIT_TOOLTIP_SECTIONS} />
            ) : null}
          </Stack>
        ))}
      </Stack>
      {error ? (
        <Typography variant="caption" color="error" role="alert">
          {error}
        </Typography>
      ) : (
        <SplitTimeline values={values} estimatedTotalRows={estimatedTotalRows} />
      )}
    </Stack>
  );
}
