import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { ConfirmActionDialog } from './confirm-action-dialog';

afterEach(() => cleanup());

describe('ConfirmActionDialog', () => {
  it('renders nothing interactive when closed', () => {
    render(
      <ThemeProvider theme={theme}>
        <ConfirmActionDialog
          open={false}
          title="Delete Training Job"
          description="Are you sure?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onCancel={vi.fn()}
          onConfirm={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.queryByText('Delete Training Job')).not.toBeInTheDocument();
  });

  it('shows the title and description when open', () => {
    render(
      <ThemeProvider theme={theme}>
        <ConfirmActionDialog
          open
          title="Delete Training Job"
          description="Permanently delete this job?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onCancel={vi.fn()}
          onConfirm={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText('Delete Training Job')).toBeInTheDocument();
    expect(screen.getByText('Permanently delete this job?')).toBeInTheDocument();
  });

  it('calls onConfirm when the confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <ConfirmActionDialog
          open
          title="Cancel Training Job"
          description="Cancel it?"
          confirmLabel="Cancel Job"
          busyLabel="Cancelling…"
          onCancel={vi.fn()}
          onConfirm={onConfirm}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Job' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when Back is clicked', () => {
    const onCancel = vi.fn();
    render(
      <ThemeProvider theme={theme}>
        <ConfirmActionDialog
          open
          title="Delete Training Job"
          description="Are you sure?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onCancel={onCancel}
          onConfirm={vi.fn()}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('disables both actions while busy and shows the busy label', () => {
    render(
      <ThemeProvider theme={theme}>
        <ConfirmActionDialog
          open
          busy
          title="Delete Training Job"
          description="Are you sure?"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          onCancel={vi.fn()}
          onConfirm={vi.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  });
});
