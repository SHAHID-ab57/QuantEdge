import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import {
  HyperparameterEditor,
  buildHyperparametersPayload,
  coerceHyperparameterValue,
  defaultKnownHyperparameterValues,
  entriesToRecord,
  knownHyperparametersAreValid,
  recordToEntries,
  type HyperparameterEntry,
} from './hyperparameter-editor';

afterEach(() => cleanup());

function renderEditor(
  knownValues: Record<string, string> = defaultKnownHyperparameterValues(),
  customEntries: HyperparameterEntry[] = [],
) {
  const onKnownChange = vi.fn();
  const onCustomChange = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <HyperparameterEditor
        knownValues={knownValues}
        onKnownChange={onKnownChange}
        customEntries={customEntries}
        onCustomChange={onCustomChange}
      />
    </ThemeProvider>,
  );
  return { onKnownChange, onCustomChange };
}

describe('coerceHyperparameterValue', () => {
  it('coerces numeric strings to numbers', () => {
    expect(coerceHyperparameterValue('5')).toBe(5);
    expect(coerceHyperparameterValue('0.01')).toBe(0.01);
  });

  it('coerces boolean-looking strings to booleans', () => {
    expect(coerceHyperparameterValue('true')).toBe(true);
    expect(coerceHyperparameterValue('false')).toBe(false);
  });

  it('leaves a non-numeric, non-boolean string as-is', () => {
    expect(coerceHyperparameterValue('adam')).toBe('adam');
  });
});

describe('entriesToRecord / recordToEntries', () => {
  it('round-trips a record through entries', () => {
    const record = entriesToRecord([{ key: 'momentum', value: '0.9' }]);
    expect(record).toEqual({ momentum: 0.9 });
    expect(recordToEntries(record)).toEqual([{ key: 'momentum', value: '0.9' }]);
  });

  it('skips entries with an empty key', () => {
    expect(entriesToRecord([{ key: '  ', value: '5' }])).toEqual({});
  });
});

describe('defaultKnownHyperparameterValues', () => {
  it('provides a default for every known hyperparameter', () => {
    const defaults = defaultKnownHyperparameterValues();
    expect(defaults.epochs).toBe('10');
    expect(defaults.learning_rate).toBe('0.001');
    expect(defaults.batch_size).toBe('32');
    expect(defaults.random_seed).toBe('42');
    expect(defaults.validation_frequency).toBe('1');
  });
});

describe('knownHyperparametersAreValid', () => {
  it('accepts the defaults', () => {
    expect(knownHyperparametersAreValid(defaultKnownHyperparameterValues())).toBe(true);
  });

  it('accepts every field left blank', () => {
    expect(
      knownHyperparametersAreValid({
        epochs: '',
        learning_rate: '',
        batch_size: '',
        random_seed: '',
        validation_frequency: '',
      }),
    ).toBe(true);
  });

  it('rejects a non-integer epochs value', () => {
    expect(
      knownHyperparametersAreValid({ ...defaultKnownHyperparameterValues(), epochs: '1.5' }),
    ).toBe(false);
  });

  it('rejects a negative learning rate', () => {
    expect(
      knownHyperparametersAreValid({ ...defaultKnownHyperparameterValues(), learning_rate: '-1' }),
    ).toBe(false);
  });

  it('rejects a non-numeric value', () => {
    expect(
      knownHyperparametersAreValid({ ...defaultKnownHyperparameterValues(), batch_size: 'abc' }),
    ).toBe(false);
  });
});

describe('buildHyperparametersPayload', () => {
  it('includes only the known fields that are non-blank, coerced to numbers', () => {
    const payload = buildHyperparametersPayload(
      {
        epochs: '5',
        learning_rate: '',
        batch_size: '32',
        random_seed: '',
        validation_frequency: '',
      },
      [],
    );
    expect(payload).toEqual({ epochs: 5, batch_size: 32 });
  });

  it('merges in custom entries', () => {
    const payload = buildHyperparametersPayload(
      { epochs: '', learning_rate: '', batch_size: '', random_seed: '', validation_frequency: '' },
      [{ key: 'optimizer', value: 'adam' }],
    );
    expect(payload).toEqual({ optimizer: 'adam' });
  });
});

describe('HyperparameterEditor', () => {
  it('renders the five known fields pre-filled with defaults', () => {
    renderEditor();
    expect(screen.getByLabelText('Epochs')).toHaveValue(10);
    expect(screen.getByLabelText('Learning rate')).toHaveValue(0.001);
    expect(screen.getByLabelText('Batch size')).toHaveValue(32);
    expect(screen.getByLabelText('Random seed')).toHaveValue(42);
    expect(screen.getByLabelText('Validation frequency')).toHaveValue(1);
  });

  it('calls onKnownChange when a known field changes', () => {
    const { onKnownChange } = renderEditor();
    fireEvent.change(screen.getByLabelText('Epochs'), { target: { value: '25' } });
    expect(onKnownChange).toHaveBeenCalledWith('epochs', '25');
  });

  it('shows a validation error for an invalid known field', () => {
    renderEditor({ ...defaultKnownHyperparameterValues(), epochs: '0' });
    expect(screen.getByText('Must be 1 or greater.')).toBeInTheDocument();
  });

  it('shows a validation error for a non-integer epochs value', () => {
    renderEditor({ ...defaultKnownHyperparameterValues(), epochs: '1.5' });
    expect(screen.getByText('Must be a whole number.')).toBeInTheDocument();
  });

  it('renders an existing custom entry', () => {
    renderEditor(defaultKnownHyperparameterValues(), [{ key: 'optimizer', value: 'adam' }]);
    expect(screen.getByLabelText('Custom parameter 1 name')).toHaveValue('optimizer');
    expect(screen.getByLabelText('Custom parameter 1 value')).toHaveValue('adam');
  });

  it('adds a new custom parameter via the name/value inputs', () => {
    const { onCustomChange } = renderEditor();
    fireEvent.change(screen.getByLabelText('New custom parameter name'), {
      target: { value: 'optimizer' },
    });
    fireEvent.change(screen.getByLabelText('New custom parameter value'), {
      target: { value: 'adam' },
    });
    fireEvent.click(screen.getByLabelText('Add custom parameter'));
    expect(onCustomChange).toHaveBeenCalledWith([{ key: 'optimizer', value: 'adam' }]);
  });

  it('disables the add button until a name is entered', () => {
    renderEditor();
    expect(screen.getByLabelText('Add custom parameter')).toBeDisabled();
  });

  it('refuses a custom parameter whose name collides with a known field', () => {
    const { onCustomChange } = renderEditor();
    fireEvent.change(screen.getByLabelText('New custom parameter name'), {
      target: { value: 'epochs' },
    });
    fireEvent.click(screen.getByLabelText('Add custom parameter'));
    expect(onCustomChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('already one of the fields above');
  });

  it('removes a custom entry', () => {
    const { onCustomChange } = renderEditor(defaultKnownHyperparameterValues(), [
      { key: 'optimizer', value: 'adam' },
    ]);
    fireEvent.click(screen.getByLabelText('Remove custom parameter optimizer'));
    expect(onCustomChange).toHaveBeenCalledWith([]);
  });

  it('editing a custom entry updates its value', () => {
    const { onCustomChange } = renderEditor(defaultKnownHyperparameterValues(), [
      { key: 'optimizer', value: 'adam' },
    ]);
    fireEvent.change(screen.getByLabelText('Custom parameter 1 value'), {
      target: { value: 'sgd' },
    });
    expect(onCustomChange).toHaveBeenCalledWith([{ key: 'optimizer', value: 'sgd' }]);
  });
});
