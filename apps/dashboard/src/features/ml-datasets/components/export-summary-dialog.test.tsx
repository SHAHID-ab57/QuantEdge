import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { ExportSummaryDialog } from './export-summary-dialog';

afterEach(() => cleanup());

function renderDialog(overrides: Partial<React.ComponentProps<typeof ExportSummaryDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const utils = render(
    <ThemeProvider theme={theme}>
      <ExportSummaryDialog
        open
        format="csv"
        rows={1000}
        columns={5}
        targetColumns={['next_close_1']}
        splitRatios={{ train: 0.7, validation: 0.15, test: 0.15 }}
        onConfirm={onConfirm}
        onCancel={onCancel}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { ...utils, onConfirm, onCancel };
}

describe('ExportSummaryDialog', () => {
  it('renders nothing when no format is pending', () => {
    renderDialog({ format: null, open: false });
    expect(screen.queryByText('Export Summary')).not.toBeInTheDocument();
  });

  it('shows rows, columns, target, split, and format', () => {
    renderDialog();
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('next_close_1')).toBeInTheDocument();
    expect(screen.getByText('70% / 15% / 15%')).toBeInTheDocument();
    expect(screen.getByText('CSV')).toBeInTheDocument();
  });

  it('shows an approximate size, labeled as approximate', () => {
    renderDialog();
    expect(screen.getByText(/rough estimate, not an exact byte count/)).toBeInTheDocument();
  });

  it('shows JSON as the format label when exporting json', () => {
    renderDialog({ format: 'json' });
    expect(screen.getByText('JSON')).toBeInTheDocument();
  });

  it('shows "None" when there are no target columns', () => {
    renderDialog({ targetColumns: [] });
    expect(screen.getByText('None')).toBeInTheDocument();
  });

  it('calls onConfirm when Export is pressed', () => {
    const { onConfirm } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Export' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when Cancel is pressed', () => {
    const { onCancel } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('disables both actions while busy, and shows an exporting label', () => {
    renderDialog({ busy: true });
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Exporting…' })).toBeDisabled();
  });
});
