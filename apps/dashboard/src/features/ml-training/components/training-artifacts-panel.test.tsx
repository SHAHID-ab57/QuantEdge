import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { theme } from '@/theme/theme';
import * as trainingApi from '@/lib/api/training';
import { downloadBlob } from '@/lib/download-file';
import { TrainingArtifactsPanel } from './training-artifacts-panel';

vi.mock('@/lib/api/training');
vi.mock('@/lib/download-file');

const mockedTrainingApi = vi.mocked(trainingApi);
const mockedDownloadBlob = vi.mocked(downloadBlob);

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function renderPanel(jobId: string, enabled: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider theme={theme}>
        <TrainingArtifactsPanel jobId={jobId} enabled={enabled} />
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe('TrainingArtifactsPanel', () => {
  it('lists every artifact with a friendly label', async () => {
    mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({
      job_id: 'job-1',
      artifacts: [
        {
          artifact_type: 'model_joblib',
          filename: 'logistic_regression-abc.joblib',
          content_type: 'application/octet-stream',
          download_url: '/api/v1/training-jobs/job-1/artifacts/model_joblib',
        },
        {
          artifact_type: 'feature_importance_csv',
          filename: 'logistic_regression-abc-feature_importance.csv',
          content_type: 'text/csv',
          download_url: '/api/v1/training-jobs/job-1/artifacts/feature_importance_csv',
        },
      ],
    });

    renderPanel('job-1', true);

    expect(await screen.findByText('Trained model (model.joblib)')).toBeInTheDocument();
    expect(screen.getByText('Feature importance (feature_importance.csv)')).toBeInTheDocument();
  });

  it('downloads an artifact when its download button is pressed', async () => {
    mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({
      job_id: 'job-1',
      artifacts: [
        {
          artifact_type: 'metrics_json',
          filename: 'metrics.json',
          content_type: 'application/json',
          download_url: '/api/v1/training-jobs/job-1/artifacts/metrics_json',
        },
      ],
    });
    const blob = new Blob(['{}'], { type: 'application/json' });
    mockedTrainingApi.downloadTrainingArtifact.mockResolvedValue(blob);

    renderPanel('job-1', true);
    fireEvent.click(await screen.findByLabelText('Download metrics.json'));

    await waitFor(() => expect(mockedDownloadBlob).toHaveBeenCalledWith(blob, 'metrics.json'));
  });

  it('renders nothing when disabled', () => {
    const { container } = renderPanel('job-1', false);
    expect(container).toBeEmptyDOMElement();
    expect(mockedTrainingApi.fetchTrainingArtifacts).not.toHaveBeenCalled();
  });

  it('renders nothing when the job has no artifacts yet', async () => {
    mockedTrainingApi.fetchTrainingArtifacts.mockResolvedValue({ job_id: 'job-1', artifacts: [] });
    const { container } = renderPanel('job-1', true);
    await waitFor(() => expect(mockedTrainingApi.fetchTrainingArtifacts).toHaveBeenCalled());
    expect(container.querySelector('ul')).not.toBeInTheDocument();
  });
});
