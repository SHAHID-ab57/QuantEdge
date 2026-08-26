import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { DeleteExperimentDialog } from './delete-experiment-dialog';

afterEach(() => cleanup());

function renderDialog(
  overrides: Partial<React.ComponentProps<typeof DeleteExperimentDialog>> = {},
) {
  const onCancel = vi.fn();
  const onConfirm = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <DeleteExperimentDialog
        open
        experimentName="baseline sma"
        onCancel={onCancel}
        onConfirm={onConfirm}
        {...overrides}
      />
    </ThemeProvider>,
  );
  return { onCancel, onConfirm };
}

describe('DeleteExperimentDialog', () => {
  it('names the experiment being deleted', () => {
    renderDialog();
    expect(screen.getByText('baseline sma')).toBeInTheDocument();
  });

  it('calls onConfirm when Delete is pressed', () => {
    const { onConfirm } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when Cancel is pressed', () => {
    const { onCancel } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('disables both actions while busy and shows a deleting label', () => {
    renderDialog({ busy: true });
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled();
  });
});
