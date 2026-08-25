import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { DatasetForm, type DatasetFormValues } from './dataset-form';

const INITIAL: DatasetFormValues = {
  market: '',
  timeframe: '',
  range: 'all',
  start: '',
  end: '',
  limit: 500,
};

function renderForm(props: Partial<React.ComponentProps<typeof DatasetForm>> = {}) {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <DatasetForm
          markets={[]}
          values={INITIAL}
          onChange={onChange}
          onSubmit={onSubmit}
          {...props}
        />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return { ...utils, onChange, onSubmit };
}

afterEach(() => cleanup());

describe('DatasetForm — tooltips', () => {
  it('explains every configurable field', () => {
    renderForm();
    expect(screen.getByRole('button', { name: 'About Market' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Timeframe' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Range' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Start' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About End' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'About Max rows' })).toBeInTheDocument();
  });

  it('still exposes the same accessible names the rest of the app already queries by', () => {
    // A tooltip must never change how an existing field is found —
    // feature-engineering-page.test.tsx and dataset-validation-page.test.tsx
    // both locate these fields by their pre-existing aria-label/label text.
    renderForm();
    expect(screen.getByRole('combobox', { name: 'Select a market' })).toBeInTheDocument();
    expect(screen.getByLabelText('Timeframe')).toBeInTheDocument();
  });
});

describe('DatasetForm — labels', () => {
  it('accepts custom submit/busy labels without changing the default caller', () => {
    renderForm({ submitLabel: 'Run Validation', busyLabel: 'Validating…' });
    expect(screen.getByRole('button', { name: 'Run Validation' })).toBeInTheDocument();
  });

  it('defaults to "Build Dataset" when no label is given', () => {
    renderForm();
    expect(screen.getByRole('button', { name: 'Build Dataset' })).toBeInTheDocument();
  });
});
