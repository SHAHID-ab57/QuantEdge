import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { Artifact } from '@/types/api/experiments';
import { ExperimentArtifactsList } from './experiment-artifacts-list';

afterEach(() => cleanup());

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: '22222222-2222-4222-8222-222222222222',
    artifact_type: 'dataset_export',
    uri: 'ETHUSD-1h-ml-dataset.csv',
    description: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderList(artifacts: Artifact[] = []) {
  const onAdd = vi.fn();
  const onDelete = vi.fn();
  render(
    <ThemeProvider theme={theme}>
      <ExperimentArtifactsList artifacts={artifacts} onAdd={onAdd} onDelete={onDelete} />
    </ThemeProvider>,
  );
  return { onAdd, onDelete };
}

describe('ExperimentArtifactsList — empty state', () => {
  it('shows a placeholder when there are no artifacts', () => {
    renderList([]);
    expect(screen.getByText('No artifacts recorded yet.')).toBeInTheDocument();
  });
});

describe('ExperimentArtifactsList — display', () => {
  it('renders each artifact’s type and uri', () => {
    renderList([artifact()]);
    const list = within(screen.getByRole('list'));
    expect(list.getByText('dataset_export')).toBeInTheDocument();
    expect(list.getByText('ETHUSD-1h-ml-dataset.csv')).toBeInTheDocument();
  });

  it('renders a description when present', () => {
    renderList([artifact({ description: 'the final export used for training' })]);
    expect(screen.getByText('the final export used for training')).toBeInTheDocument();
  });
});

describe('ExperimentArtifactsList — adding an artifact', () => {
  it('disables Add Artifact until a uri is entered', () => {
    renderList([]);
    expect(screen.getByRole('button', { name: 'Add Artifact' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Artifact URI'), { target: { value: 'report.pdf' } });
    expect(screen.getByRole('button', { name: 'Add Artifact' })).not.toBeDisabled();
  });

  it('calls onAdd with the entered type/uri/description and clears the form', () => {
    const { onAdd } = renderList([]);
    fireEvent.change(screen.getByLabelText('Artifact URI'), { target: { value: 'report.pdf' } });
    fireEvent.change(screen.getByLabelText('Artifact description'), {
      target: { value: 'final report' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add Artifact' }));

    expect(onAdd).toHaveBeenCalledWith({
      artifact_type: 'dataset_export',
      uri: 'report.pdf',
      description: 'final report',
    });
    expect(screen.getByLabelText('Artifact URI')).toHaveValue('');
  });

  it('defaults artifact_type to dataset_export and lets it be changed', () => {
    const { onAdd } = renderList([]);
    fireEvent.mouseDown(screen.getByLabelText('Type'));
    fireEvent.click(screen.getByRole('option', { name: 'report' }));
    fireEvent.change(screen.getByLabelText('Artifact URI'), { target: { value: 'x.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Artifact' }));

    expect(onAdd).toHaveBeenCalledWith({
      artifact_type: 'report',
      uri: 'x.pdf',
      description: null,
    });
  });
});

describe('ExperimentArtifactsList — deleting an artifact', () => {
  it('calls onDelete with the artifact id', () => {
    const { onDelete } = renderList([artifact()]);
    fireEvent.click(
      screen.getByRole('button', { name: 'Delete artifact ETHUSD-1h-ml-dataset.csv' }),
    );
    expect(onDelete).toHaveBeenCalledWith('22222222-2222-4222-8222-222222222222');
  });
});
