'use client';

import DeleteIcon from '@mui/icons-material/Delete';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Section } from '@/components/section';
import type { ExperimentStatus } from '@/types/api/experiments';
import { DeleteExperimentDialog } from './components/delete-experiment-dialog';
import { ExperimentConfigDialog } from './components/experiment-config-dialog';
import { ExperimentArtifactsList } from './components/experiment-artifacts-list';
import { ExperimentMetadataPanel } from './components/experiment-metadata-panel';
import { ExperimentMetricsTable } from './components/experiment-metrics-table';
import { ExperimentNotesCard } from './components/experiment-notes-card';
import { ExperimentStatusChip } from './components/experiment-status-chip';
import { ExperimentTagsEditor } from './components/experiment-tags-editor';
import {
  useCreateArtifact,
  useCreateMetric,
  useDeleteArtifact,
  useDeleteExperiment,
  useDeleteMetric,
  useExperiment,
  useUpdateExperiment,
} from './hooks/use-experiments-data';

export interface ExperimentDetailPageProps {
  experimentId: string;
}

function PageSkeleton() {
  return (
    <Stack spacing={2} role="status" aria-label="Loading experiment">
      <Skeleton variant="rounded" height={72} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Skeleton variant="rounded" height={320} />
        </Grid>
        <Grid size={{ xs: 12, md: 7 }}>
          <Skeleton variant="rounded" height={320} />
        </Grid>
      </Grid>
    </Stack>
  );
}

/**
 * One experiment's full record: metadata (reproducibility fields plus an
 * editable status), notes, tags, a metrics table, and an artifact
 * reference list. Every mutation here (status, notes, tags, add/delete
 * metric, add/delete artifact) goes straight through the same
 * `PATCH`/`POST`/`DELETE` endpoints the list page's own create action
 * uses — there is no separate "draft" state held only in this page.
 */
export function ExperimentDetailPage({ experimentId }: ExperimentDetailPageProps) {
  const router = useRouter();
  const experiment = useExperiment(experimentId);
  const update = useUpdateExperiment();
  const remove = useDeleteExperiment();
  const createMetric = useCreateMetric();
  const deleteMetric = useDeleteMetric();
  const createArtifact = useCreateArtifact();
  const deleteArtifact = useDeleteArtifact();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  if (experiment.isLoading) {
    return <PageSkeleton />;
  }

  if (experiment.isError || !experiment.data) {
    return (
      <Alert
        severity="error"
        role="alert"
        action={<Button onClick={() => experiment.refetch()}>Retry</Button>}
      >
        {experiment.error instanceof Error
          ? experiment.error.message
          : 'Could not load this experiment.'}
      </Alert>
    );
  }

  const data = experiment.data;

  return (
    <Stack spacing={2}>
      <Section
        title={data.name}
        subtitle={`Experiment ${data.id}`}
        action={
          <Stack direction="row" spacing={1} alignItems="center">
            <ExperimentStatusChip status={data.status} />
            <Button
              size="small"
              color="error"
              variant="outlined"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </Stack>
        }
      >
        <Typography variant="body2" color="text.secondary">
          Dataset version: {data.dataset_version ?? 'Not recorded'}
        </Typography>
      </Section>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Stack spacing={2}>
            <Section title="Metadata" subtitle="The reproducibility record for this experiment">
              <ExperimentMetadataPanel
                experiment={data}
                statusUpdating={update.isPending}
                onStatusChange={(status: ExperimentStatus) =>
                  update.mutate({ id: data.id, body: { status } })
                }
                onEditConfig={() => setConfigOpen(true)}
              />
            </Section>

            <Section title="Notes">
              <ExperimentNotesCard
                notes={data.notes}
                saving={update.isPending}
                onSave={(notes) => update.mutate({ id: data.id, body: { notes: notes || null } })}
              />
            </Section>

            <Section title="Tags">
              <ExperimentTagsEditor
                tags={data.tags}
                disabled={update.isPending}
                onChange={(tags) => update.mutate({ id: data.id, body: { tags } })}
              />
            </Section>
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Stack spacing={2}>
            <Section title="Metrics" subtitle="Evaluation results recorded against this experiment">
              <ExperimentMetricsTable
                metrics={data.metrics}
                adding={createMetric.isPending}
                onAdd={(metric) => createMetric.mutate({ experimentId: data.id, body: metric })}
                onDelete={(metricId) => deleteMetric.mutate({ experimentId: data.id, metricId })}
              />
            </Section>

            <Section
              title="Artifacts"
              subtitle="References to files, reports, or exports this experiment produced"
            >
              <ExperimentArtifactsList
                artifacts={data.artifacts}
                adding={createArtifact.isPending}
                onAdd={(artifact) =>
                  createArtifact.mutate({ experimentId: data.id, body: artifact })
                }
                onDelete={(artifactId) =>
                  deleteArtifact.mutate({ experimentId: data.id, artifactId })
                }
              />
            </Section>
          </Stack>
        </Grid>
      </Grid>

      <DeleteExperimentDialog
        open={deleteOpen}
        experimentName={data.name}
        busy={remove.isPending}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => {
          remove.mutate(data.id, {
            onSuccess: () => router.push('/experiments'),
          });
        }}
      />

      <ExperimentConfigDialog
        open={configOpen}
        experiment={data}
        onClose={() => setConfigOpen(false)}
      />
    </Stack>
  );
}
