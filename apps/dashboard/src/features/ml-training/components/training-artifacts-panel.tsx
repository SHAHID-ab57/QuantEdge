'use client';

import DownloadIcon from '@mui/icons-material/Download';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { downloadTrainingArtifact } from '@/lib/api/training';
import { downloadBlob } from '@/lib/download-file';
import { useTrainingArtifacts } from '../hooks/use-training-jobs-data';

export interface TrainingArtifactsPanelProps {
  jobId: string;
  enabled: boolean;
}

const ARTIFACT_LABELS: Record<string, string> = {
  model_joblib: 'Trained model (model.joblib)',
  metrics_json: 'Metrics (metrics.json)',
  training_report_json: 'Full training report (training_report.json)',
  feature_importance_csv: 'Feature importance (feature_importance.csv)',
  confusion_matrix_png: 'Confusion matrix (confusion_matrix.png)',
  roc_curve_png: 'ROC curve (roc_curve.png)',
  precision_recall_curve_png: 'Precision-Recall curve (precision_recall_curve.png)',
};

/**
 * Every downloadable file a completed job's training run produced — the
 * Artifact Management requirement. Fetched from `GET
 * /training-jobs/{id}/artifacts` (only once the job has actually run, since
 * a pending job has none) and downloaded through the same blob pattern the
 * ML Dataset Builder's export already uses.
 */
export function TrainingArtifactsPanel({ jobId, enabled }: TrainingArtifactsPanelProps) {
  const artifacts = useTrainingArtifacts(jobId, enabled);

  if (!enabled) return null;
  if (artifacts.isLoading) {
    return (
      <Typography variant="body2" color="text.secondary">
        Loading artifacts…
      </Typography>
    );
  }
  if (!artifacts.data || artifacts.data.artifacts.length === 0) {
    return null;
  }

  const handleDownload = async (downloadUrl: string, filename: string) => {
    const blob = await downloadTrainingArtifact(downloadUrl);
    downloadBlob(blob, filename);
  };

  return (
    <Stack spacing={0.5}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        Downloadable Artifacts
      </Typography>
      <List dense disablePadding>
        {artifacts.data.artifacts.map((artifact) => (
          <ListItem
            key={artifact.artifact_type}
            disableGutters
            secondaryAction={
              <Tooltip title={`Download ${artifact.filename}`}>
                <IconButton
                  edge="end"
                  aria-label={`Download ${artifact.filename}`}
                  onClick={() => handleDownload(artifact.download_url, artifact.filename)}
                >
                  <DownloadIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            }
          >
            <ListItemText
              primary={ARTIFACT_LABELS[artifact.artifact_type] ?? artifact.filename}
              secondary={artifact.content_type}
            />
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
