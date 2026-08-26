import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import { ExperimentNotesCard } from './experiment-notes-card';

afterEach(() => cleanup());

function renderCard(notes: string | null = null, saving = false) {
  const onSave = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <ExperimentNotesCard notes={notes} onSave={onSave} saving={saving} />
    </ThemeProvider>,
  );
  return onSave;
}

describe('ExperimentNotesCard', () => {
  it('shows a placeholder when there are no notes yet', () => {
    renderCard(null);
    expect(screen.getByText('No notes yet.')).toBeInTheDocument();
  });

  it('shows the existing notes', () => {
    renderCard('promising first attempt');
    expect(screen.getByText('promising first attempt')).toBeInTheDocument();
  });

  it('enters edit mode when Edit is clicked, seeded with the current notes', () => {
    renderCard('existing notes');
    fireEvent.click(screen.getByRole('button', { name: 'Edit notes' }));
    expect(screen.getByLabelText('Notes')).toHaveValue('existing notes');
  });

  it('calls onSave with the edited text and exits edit mode', () => {
    const onSave = renderCard('old');
    fireEvent.click(screen.getByRole('button', { name: 'Edit notes' }));
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'new notes' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(onSave).toHaveBeenCalledWith('new notes');
    expect(screen.queryByLabelText('Notes')).not.toBeInTheDocument();
  });

  it('discards changes when Cancel is pressed', () => {
    const onSave = renderCard('old');
    fireEvent.click(screen.getByRole('button', { name: 'Edit notes' }));
    fireEvent.change(screen.getByLabelText('Notes'), { target: { value: 'discarded' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('old')).toBeInTheDocument();
  });

  it('disables Save and Cancel while saving', () => {
    renderCard('old', true);
    fireEvent.click(screen.getByRole('button', { name: 'Edit notes' }));
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});
