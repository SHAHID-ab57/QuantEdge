'use client';

import CancelIcon from '@mui/icons-material/Cancel';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import DoNotDisturbOnIcon from '@mui/icons-material/DoNotDisturbOn';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { TrainingJobStage, TrainingJobStatus } from '@/types/api/training';
import { STAGE_ORDER } from '../lib/training-job-status';

type StepState = 'done' | 'active' | 'error' | 'cancelled' | 'pending';

interface TimelineStep {
  label: string;
  state: StepState;
}

function computeSteps(
  status: TrainingJobStatus,
  currentStage: TrainingJobStage | null,
): TimelineStep[] {
  const stageIndex = currentStage
    ? STAGE_ORDER.findIndex((stage) => stage.key === currentStage)
    : -1;

  const stageStates: StepState[] = STAGE_ORDER.map((_, index) => {
    if (status === 'completed') return 'done';
    if (status === 'failed') {
      if (index < stageIndex) return 'done';
      if (index === stageIndex) return 'error';
      return 'pending';
    }
    if (status === 'cancelled') {
      return index < stageIndex ? 'done' : 'cancelled';
    }
    if (status === 'running') {
      if (index < stageIndex) return 'done';
      if (index === stageIndex) return 'active';
      return 'pending';
    }
    return 'pending'; // pending status: no stage reached yet
  });

  let completedState: StepState = 'pending';
  if (status === 'completed') completedState = 'done';
  else if (status === 'cancelled') completedState = 'cancelled';

  return [
    { label: 'Pending', state: 'done' },
    ...STAGE_ORDER.map((stage, index) => ({
      label: stage.label,
      state: stageStates[index] ?? 'pending',
    })),
    { label: 'Completed', state: completedState },
  ];
}

function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case 'done':
      return <CheckCircleIcon fontSize="small" color="success" aria-hidden />;
    case 'active':
      return <CircularProgress size={16} thickness={6} aria-hidden />;
    case 'error':
      return <CancelIcon fontSize="small" color="error" aria-hidden />;
    case 'cancelled':
      return <DoNotDisturbOnIcon fontSize="small" color="disabled" aria-hidden />;
    case 'pending':
    default:
      return <RadioButtonUncheckedIcon fontSize="small" color="disabled" aria-hidden />;
  }
}

const STATE_TEXT_COLOR: Record<StepState, string> = {
  done: 'text.primary',
  active: 'primary.main',
  error: 'error.main',
  cancelled: 'text.disabled',
  pending: 'text.disabled',
};

export interface TrainingJobStageTimelineProps {
  status: TrainingJobStatus;
  currentStage: TrainingJobStage | null;
}

/**
 * A checklist-style visualization of the job's lifecycle and pipeline
 * stages, replacing a plain status chip — the exact 8-step sequence a
 * status monitor needs to answer "how far did this get, and where did it
 * stop" at a glance: `Pending → Dataset Validation → Dataset Loaded →
 * Model Initialized → Training → Saving Results → Experiment Updated →
 * Completed`. `status`/`currentStage` are the same two `TrainingJob`
 * fields the plain chip already read — this is a richer view over
 * existing data, not new state.
 */
export function TrainingJobStageTimeline({ status, currentStage }: TrainingJobStageTimelineProps) {
  const steps = computeSteps(status, currentStage);

  return (
    <Stack
      component="ol"
      spacing={0.75}
      sx={{ listStyle: 'none', m: 0, p: 0 }}
      aria-label="Training pipeline progress"
    >
      {steps.map((step) => (
        <Stack
          component="li"
          key={step.label}
          direction="row"
          spacing={1}
          alignItems="center"
          aria-current={step.state === 'active' ? 'step' : undefined}
        >
          <Box sx={{ display: 'flex', width: 18, justifyContent: 'center' }}>
            <StepIcon state={step.state} />
          </Box>
          <Typography
            variant="body2"
            sx={{
              color: STATE_TEXT_COLOR[step.state],
              fontWeight: step.state === 'active' ? 700 : 400,
            }}
          >
            {step.label}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}
