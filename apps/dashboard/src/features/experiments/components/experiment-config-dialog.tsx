'use client';

import DownloadIcon from '@mui/icons-material/Download';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { InfoTooltip } from '@/components/info-tooltip';
import { FeatureSelector } from '@/features/feature-engineering/components/feature-selector';
import {
  toggleSelection,
  updateSelectionParams,
  type FeatureSelection,
} from '@/features/feature-engineering/lib/feature-selection';
import { SplitConfigForm } from '@/features/ml-datasets/components/split-config-form';
import { TargetSelector } from '@/features/ml-datasets/components/target-selector';
import {
  validateSplitRatios,
  type SplitRatioValues,
} from '@/features/ml-datasets/lib/split-ratios';
import {
  toggleTargetSelection,
  updateTargetSelectionParams,
  type TargetSelection,
} from '@/features/ml-datasets/lib/target-selection';
import { fetchFeatures } from '@/lib/api/features';
import { fetchMLDatasetBuild, fetchTargets } from '@/lib/api/ml-datasets';
import type { Experiment } from '@/types/api/experiments';
import type { Feature } from '@/types/api/features';
import type { TargetDTO } from '@/types/api/ml-datasets';
import { useUpdateExperiment } from '../hooks/use-experiments-data';
import {
  buildExperimentConfigPatch,
  datasetBuildToConfig,
  experimentToFeatureSelections,
  experimentToSplitValues,
  experimentToTargetSelections,
} from '../lib/experiment-config';

export interface ExperimentConfigDialogProps {
  open: boolean;
  experiment: Experiment;
  onClose: () => void;
}

/** One unrecognized recorded name, with a way to drop it — `FeatureSelector`/
 * `TargetSelector` only ever render rows from the live catalogue, so a stale
 * or hand-typed name from a curl-PATCH era record has no checkbox of its own
 * to untick; this is the only way to remove one. */
function UnknownEntriesAlert({
  label,
  names,
  onRemove,
}: {
  label: string;
  names: string[];
  onRemove: (name: string) => void;
}) {
  if (names.length === 0) {
    return null;
  }
  return (
    <Alert severity="warning" role="alert">
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {names.length} recorded {label}
        {names.length === 1 ? '' : 's'} {names.length === 1 ? "isn't" : "aren't"} in the current
        catalogue — remove {names.length === 1 ? 'it' : 'them'} before saving.
      </Typography>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
        {names.map((name) => (
          <Chip key={name} size="small" label={name} onDelete={() => onRemove(name)} />
        ))}
      </Stack>
    </Alert>
  );
}

/**
 * Edits an experiment's `feature_set`/`target_config`/`split_config` — the
 * reproducibility record `ExperimentMetadataPanel` otherwise only displays.
 * Composed entirely from components that already exist and are already
 * tested elsewhere: `FeatureSelector` (feature-engineering, reused verbatim
 * by `/features` and `/validation`), `TargetSelector` and `SplitConfigForm`
 * (ml-datasets, reused verbatim by `/ml-datasets`). No new picker is built
 * here — this dialog only pre-populates them from the experiment and wires
 * their combined state onto `PATCH /experiments/{id}`, in the exact
 * `{feature_set, target_config, split_config}` shape the ML Dataset
 * Builder's own request already produces (`buildExperimentConfigPatch`).
 *
 * Before this existed, the only way to set these three fields was a
 * hand-written `curl -X PATCH` — a training job could reach `Run` several
 * pipeline stages deep before discovering nothing was ever recorded. This
 * closes that gap without changing the backend at all: `feature_set`/
 * `target_config` stay free JSON server-side.
 *
 * A selected name is always valid *going forward* — `FeatureSelector`/
 * `TargetSelector` only ever render rows from the live `GET /features`/
 * `GET /ml/targets` catalogues — but a record set by hand before this
 * editor existed can cite a name that catalogue no longer has (renamed,
 * removed, or simply mistyped). `UnknownEntriesAlert` surfaces exactly
 * those and blocks Save until they're removed, so a stale name can never
 * be re-saved silently.
 */
export function ExperimentConfigDialog({ open, experiment, onClose }: ExperimentConfigDialogProps) {
  const update = useUpdateExperiment();

  // Gated by `enabled: open`, the same way `CreateTrainingJobDialog` gates
  // its own `markets`/`timeframes` queries — this dialog is mounted
  // unconditionally by `ExperimentDetailPage` (so it can be opened
  // instantly), and must not fetch the catalogues until it actually opens.
  // Query keys intentionally match `useFeatureCatalog`/`useTargetCatalog`
  // exactly, so the cache is shared with `/features`, `/validation`, and
  // `/ml-datasets` if already warm.
  const featureCatalogue = useQuery({
    queryKey: ['features', 'catalogue'],
    queryFn: fetchFeatures,
    enabled: open,
    staleTime: 5 * 60_000,
  });
  const targetCatalogue = useQuery({
    queryKey: ['ml-datasets', 'targets'],
    queryFn: fetchTargets,
    enabled: open,
    staleTime: 5 * 60_000,
  });

  const features = useMemo(() => featureCatalogue.data?.features ?? [], [featureCatalogue.data]);
  const targets = useMemo(() => targetCatalogue.data?.targets ?? [], [targetCatalogue.data]);

  const [featureSelections, setFeatureSelections] = useState<FeatureSelection[]>([]);
  const [targetSelections, setTargetSelections] = useState<TargetSelection[]>([]);
  const [split, setSplit] = useState<SplitRatioValues>(experimentToSplitValues(experiment));

  const [importBuildId, setImportBuildId] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const importBuild = useMutation({ mutationFn: (id: string) => fetchMLDatasetBuild(id) });

  // Re-populate from the experiment's current record every time the dialog
  // opens — never reactively while it stays open, so an in-progress edit
  // is never clobbered by a background refetch of the same experiment.
  useEffect(() => {
    if (!open) return;
    setFeatureSelections(experimentToFeatureSelections(experiment));
    setTargetSelections(experimentToTargetSelections(experiment));
    setSplit(experimentToSplitValues(experiment));
    setImportBuildId('');
    setImportError(null);
    importBuild.reset();
    update.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reinitialize only on open, not per keystroke
  }, [open, experiment]);

  const handleFeatureToggle = (feature: Feature) =>
    setFeatureSelections((current) => toggleSelection(current, feature));
  const handleFeatureParamsChange = (feature: string, params: Record<string, string>) =>
    setFeatureSelections((current) => updateSelectionParams(current, feature, params));
  const handleTargetToggle = (target: TargetDTO) =>
    setTargetSelections((current) => toggleTargetSelection(current, target));
  const handleTargetParamsChange = (target: string, params: Record<string, string>) =>
    setTargetSelections((current) => updateTargetSelectionParams(current, target, params));

  const catalogueLoading = featureCatalogue.isLoading || targetCatalogue.isLoading;

  const unknownFeatures = useMemo(
    () =>
      catalogueLoading
        ? []
        : featureSelections
            .filter((selection) => !features.some((feature) => feature.name === selection.feature))
            .map((selection) => selection.feature),
    [catalogueLoading, featureSelections, features],
  );
  const unknownTargets = useMemo(
    () =>
      catalogueLoading
        ? []
        : targetSelections
            .filter((selection) => !targets.some((target) => target.name === selection.target))
            .map((selection) => selection.target),
    [catalogueLoading, targetSelections, targets],
  );

  const removeUnknownFeature = (name: string) =>
    setFeatureSelections((current) => current.filter((selection) => selection.feature !== name));
  const removeUnknownTarget = (name: string) =>
    setTargetSelections((current) => current.filter((selection) => selection.target !== name));

  const splitError = validateSplitRatios(split);
  const hasUnknownEntries = unknownFeatures.length > 0 || unknownTargets.length > 0;
  const canSave =
    !catalogueLoading && !hasUnknownEntries && splitError === null && !update.isPending;

  const handleImport = async () => {
    const id = importBuildId.trim();
    if (!id) return;
    setImportError(null);
    try {
      const detail = await importBuild.mutateAsync(id);
      const config = datasetBuildToConfig(detail.dataset);
      setFeatureSelections(config.features);
      setTargetSelections(config.targets);
      setSplit(config.split);
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Could not load that dataset build.');
    }
  };

  const handleSave = async () => {
    if (!canSave) return;
    await update.mutateAsync({
      id: experiment.id,
      body: buildExperimentConfigPatch(featureSelections, targetSelections, split),
    });
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Edit Configuration — {experiment.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Stack spacing={1}>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Typography variant="subtitle2">Import from Dataset History</Typography>
              <InfoTooltip
                label="Import from Dataset History"
                sections={[
                  {
                    heading: 'What it does',
                    body: 'Fetches one past ML dataset build and pre-fills its features, targets, and split ratios below — the same values that build actually ran with.',
                  },
                  {
                    heading: 'Where to find a build id',
                    body: 'The Dataset History table on /ml-datasets — open a row and copy its id, or use the id shown on a freshly built dataset.',
                  },
                ]}
              />
            </Stack>
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                size="small"
                label="Dataset build ID"
                value={importBuildId}
                onChange={(event) => setImportBuildId(event.target.value)}
                placeholder="From Dataset History, e.g. 9c1e4a2c-..."
                helperText="Pre-fills features, targets, and split below from a past dataset build."
                sx={{ flex: 1 }}
                slotProps={{ htmlInput: { 'aria-label': 'Dataset build ID' } }}
              />
              <Button
                variant="outlined"
                onClick={handleImport}
                disabled={!importBuildId.trim() || importBuild.isPending}
                startIcon={<DownloadIcon fontSize="small" />}
              >
                {importBuild.isPending ? 'Loading…' : 'Import'}
              </Button>
            </Stack>
            {importError ? (
              <Alert severity="error" role="alert">
                {importError}
              </Alert>
            ) : null}
          </Stack>

          <Divider />

          <Typography variant="subtitle2">Features</Typography>
          <FeatureSelector
            features={features}
            loading={featureCatalogue.isLoading}
            selections={featureSelections}
            onToggle={handleFeatureToggle}
            onParamsChange={handleFeatureParamsChange}
          />
          <UnknownEntriesAlert
            label="feature"
            names={unknownFeatures}
            onRemove={removeUnknownFeature}
          />

          <Divider />

          <Typography variant="subtitle2">Prediction Targets</Typography>
          <TargetSelector
            targets={targets}
            loading={targetCatalogue.isLoading}
            selections={targetSelections}
            onToggle={handleTargetToggle}
            onParamsChange={handleTargetParamsChange}
          />
          <UnknownEntriesAlert
            label="target"
            names={unknownTargets}
            onRemove={removeUnknownTarget}
          />

          <Divider />

          <Typography variant="subtitle2">Split Configuration</Typography>
          <SplitConfigForm values={split} onChange={setSplit} />

          {update.isError ? (
            <Alert severity="error" role="alert">
              {update.error instanceof Error
                ? update.error.message
                : 'Could not save this configuration.'}
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSave} disabled={!canSave}>
          {update.isPending ? 'Saving…' : 'Save Configuration'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
