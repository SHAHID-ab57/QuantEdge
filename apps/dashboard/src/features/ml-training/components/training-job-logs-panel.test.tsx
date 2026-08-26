import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import type { TrainingJobLog } from '@/types/api/training';
import { TrainingJobLogsPanel } from './training-job-logs-panel';

afterEach(() => cleanup());

const LOGS: TrainingJobLog[] = [
  {
    id: 'log-1',
    level: 'info',
    stage: 'validate_dataset',
    message: 'Starting stage: validate_dataset',
    logged_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'log-2',
    level: 'error',
    stage: 'execute_training',
    message: 'Stage failed: boom',
    logged_at: '2026-01-01T00:00:05Z',
  },
];

function renderPanel(
  logs: TrainingJobLog[] = LOGS,
  status: 'pending' | 'running' | 'completed' = 'completed',
) {
  render(
    <ThemeProvider theme={theme}>
      <TrainingJobLogsPanel jobId="job-1" logs={logs} status={status} />
    </ThemeProvider>,
  );
}

describe('TrainingJobLogsPanel', () => {
  it('shows an empty message when there are no logs', () => {
    renderPanel([]);
    expect(screen.getByText(/No logs yet/)).toBeInTheDocument();
  });

  it('renders every log line with its level and stage', () => {
    renderPanel();
    expect(screen.getByText('Starting stage: validate_dataset')).toBeInTheDocument();
    expect(screen.getByText('Stage failed: boom')).toBeInTheDocument();
    expect(screen.getByText('Dataset Validation')).toBeInTheDocument();
    expect(screen.getByText('Training')).toBeInTheDocument();
  });

  it('filters logs by the search box', () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Search logs'), { target: { value: 'boom' } });
    expect(screen.queryByText('Starting stage: validate_dataset')).not.toBeInTheDocument();
    expect(screen.getByText('Stage failed: boom')).toBeInTheDocument();
  });

  it('shows a no-match message when the search filters out everything', () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText('Search logs'), { target: { value: 'nonexistent' } });
    expect(screen.getByText(/No log lines match/)).toBeInTheDocument();
  });

  it('collapses and expands the log list', async () => {
    renderPanel();
    expect(screen.getByText('Stage failed: boom')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Collapse logs'));
    await waitFor(() => expect(screen.queryByText('Stage failed: boom')).not.toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Expand logs'));
    expect(await screen.findByText('Stage failed: boom')).toBeInTheDocument();
  });

  it('copies logs to the clipboard', () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Copy logs' }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0]?.[0]).toContain('Stage failed: boom');
  });

  it('disables copy and download when there are no logs', () => {
    renderPanel([]);
    expect(screen.getByRole('button', { name: 'Copy logs' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Download logs' })).toBeDisabled();
  });

  it('shows the log count in the heading', () => {
    renderPanel();
    expect(screen.getByText('Logs (2)')).toBeInTheDocument();
  });
});
