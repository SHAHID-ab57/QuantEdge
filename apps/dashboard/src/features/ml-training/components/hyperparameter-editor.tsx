'use client';

import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import {
  KNOWN_HYPERPARAMETER_KEYS,
  KNOWN_HYPERPARAMETER_SPECS,
  validateHyperparameterValue,
} from '../lib/hyperparameter-specs';
import { HYPERPARAMETERS_FIELD_HELP } from '../lib/training-job-help';

export interface HyperparameterEntry {
  key: string;
  value: string;
}

/** Coerces a hyperparameter's typed-in text into a number/boolean when it unambiguously
 * looks like one, otherwise leaves it as a string — arbitrary JSON scalars, matching
 * the backend's `hyperparameters: dict[str, Any]` contract. */
export function coerceHyperparameterValue(raw: string): string | number | boolean {
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  if (raw.trim() !== '' && !Number.isNaN(Number(raw))) return Number(raw);
  return raw;
}

export function entriesToRecord(entries: HyperparameterEntry[]): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  for (const entry of entries) {
    const key = entry.key.trim();
    if (key.length === 0) continue;
    record[key] = coerceHyperparameterValue(entry.value);
  }
  return record;
}

export function recordToEntries(record: Record<string, unknown>): HyperparameterEntry[] {
  return Object.entries(record).map(([key, value]) => ({ key, value: String(value) }));
}

/** Default text-field values for every known hyperparameter, pre-filled so a researcher
 * sees a sensible starting point rather than a blank required-looking field. */
export function defaultKnownHyperparameterValues(): Record<string, string> {
  return Object.fromEntries(
    KNOWN_HYPERPARAMETER_SPECS.map((spec) => [spec.key, String(spec.default)]),
  );
}

/** Whether every known field currently holds a valid value (blank is valid — it's omitted). */
export function knownHyperparametersAreValid(knownValues: Record<string, string>): boolean {
  return KNOWN_HYPERPARAMETER_SPECS.every(
    (spec) => validateHyperparameterValue(spec, knownValues[spec.key] ?? '') === null,
  );
}

/** Merges the known numeric fields (blank omitted) with the custom key/value list into
 * the payload sent as `hyperparameters`. */
export function buildHyperparametersPayload(
  knownValues: Record<string, string>,
  customEntries: HyperparameterEntry[],
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const spec of KNOWN_HYPERPARAMETER_SPECS) {
    const raw = (knownValues[spec.key] ?? '').trim();
    if (raw === '') continue;
    payload[spec.key] = Number(raw);
  }
  return { ...payload, ...entriesToRecord(customEntries) };
}

export interface HyperparameterEditorProps {
  knownValues: Record<string, string>;
  onKnownChange: (key: string, value: string) => void;
  customEntries: HyperparameterEntry[];
  onCustomChange: (entries: HyperparameterEntry[]) => void;
}

/**
 * The five parameters `PlaceholderModelAdapter` (and any future real model
 * adapter) is expected to read get dedicated, validated numeric fields with
 * defaults and tooltips; anything else is a generic key/value "custom
 * parameter," since the framework has no fixed hyperparameter schema beyond
 * these five — a future model adapter's own extra knobs have nowhere else
 * to go but a free-form list.
 */
export function HyperparameterEditor({
  knownValues,
  onKnownChange,
  customEntries,
  onCustomChange,
}: HyperparameterEditorProps) {
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [customKeyError, setCustomKeyError] = useState<string | null>(null);

  const addCustomEntry = (key: string, value = '') => {
    const trimmed = key.trim();
    if (trimmed.length === 0) return;
    if (KNOWN_HYPERPARAMETER_KEYS.has(trimmed)) {
      setCustomKeyError(`"${trimmed}" is already one of the fields above.`);
      return;
    }
    if (customEntries.some((entry) => entry.key === trimmed)) {
      setCustomKeyError(`"${trimmed}" has already been added.`);
      return;
    }
    setCustomKeyError(null);
    onCustomChange([...customEntries, { key: trimmed, value }]);
    setNewKey('');
    setNewValue('');
  };

  const updateCustomEntry = (index: number, patch: Partial<HyperparameterEntry>) => {
    onCustomChange(customEntries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)));
  };

  const removeCustomEntry = (index: number) => {
    onCustomChange(customEntries.filter((_, i) => i !== index));
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Typography variant="subtitle2">Hyperparameters</Typography>
        <InfoTooltip label="Hyperparameters" sections={HYPERPARAMETERS_FIELD_HELP} />
      </Stack>

      <Stack spacing={1.5}>
        {KNOWN_HYPERPARAMETER_SPECS.map((spec) => {
          const value = knownValues[spec.key] ?? '';
          const error = validateHyperparameterValue(spec, value);
          return (
            <Stack key={spec.key} direction="row" spacing={0.5} alignItems="flex-start">
              <TextField
                type="number"
                size="small"
                label={spec.label}
                value={value}
                onChange={(event) => onKnownChange(spec.key, event.target.value)}
                error={Boolean(error)}
                helperText={error ?? ' '}
                slotProps={{
                  htmlInput: { step: spec.step ?? (spec.integer ? 1 : 'any'), min: spec.min },
                }}
                sx={{ flex: 1 }}
              />
              <InfoTooltip
                label={spec.label}
                sections={[{ heading: spec.label, body: spec.help }]}
              />
            </Stack>
          );
        })}
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Custom parameters
      </Typography>
      {customEntries.map((entry, index) => (
        <Stack direction="row" spacing={1} key={index} alignItems="center">
          <TextField
            size="small"
            label="Name"
            value={entry.key}
            onChange={(event) => updateCustomEntry(index, { key: event.target.value })}
            slotProps={{ htmlInput: { 'aria-label': `Custom parameter ${index + 1} name` } }}
          />
          <TextField
            size="small"
            label="Value"
            value={entry.value}
            onChange={(event) => updateCustomEntry(index, { value: event.target.value })}
            slotProps={{ htmlInput: { 'aria-label': `Custom parameter ${index + 1} value` } }}
          />
          <IconButton
            size="small"
            aria-label={`Remove custom parameter ${entry.key || index + 1}`}
            onClick={() => removeCustomEntry(index)}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField
          size="small"
          label="New name"
          value={newKey}
          onChange={(event) => {
            setNewKey(event.target.value);
            setCustomKeyError(null);
          }}
          slotProps={{ htmlInput: { 'aria-label': 'New custom parameter name' } }}
        />
        <TextField
          size="small"
          label="New value"
          value={newValue}
          onChange={(event) => setNewValue(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'New custom parameter value' } }}
        />
        <IconButton
          size="small"
          aria-label="Add custom parameter"
          onClick={() => addCustomEntry(newKey, newValue)}
          disabled={newKey.trim().length === 0}
        >
          <AddIcon fontSize="small" />
        </IconButton>
      </Stack>
      {customKeyError ? (
        <Alert severity="warning" role="alert" sx={{ py: 0 }}>
          {customKeyError}
        </Alert>
      ) : null}
      {customEntries.length === 0 && customKeyError === null ? (
        <Chip
          size="small"
          variant="outlined"
          label="No custom parameters — the placeholder adapter ignores unknown values"
          sx={{ alignSelf: 'flex-start' }}
        />
      ) : null}
    </Stack>
  );
}
