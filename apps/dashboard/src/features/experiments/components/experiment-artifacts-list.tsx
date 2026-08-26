'use client';

import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { ARTIFACT_TYPES, type Artifact, type ArtifactType } from '@/types/api/experiments';

export interface ExperimentArtifactsListProps {
  artifacts: Artifact[];
  onAdd: (artifact: {
    artifact_type: ArtifactType;
    uri: string;
    description: string | null;
  }) => void;
  onDelete: (artifactId: string) => void;
  adding?: boolean;
}

/**
 * Every artifact *reference* this experiment produced — a file path,
 * export filename, or URL, never the file's actual bytes (this platform
 * has no object storage wired in yet; see `ARCHITECTURE.md` § "Known
 * Limitations"). A `dataset_export` entry here would typically be the
 * filename an ML Dataset Builder export was saved as.
 */
export function ExperimentArtifactsList({
  artifacts,
  onAdd,
  onDelete,
  adding = false,
}: ExperimentArtifactsListProps) {
  const [artifactType, setArtifactType] = useState<ArtifactType>('dataset_export');
  const [uri, setUri] = useState('');
  const [description, setDescription] = useState('');

  const canAdd = uri.trim().length > 0;

  const handleAdd = () => {
    onAdd({
      artifact_type: artifactType,
      uri: uri.trim(),
      description: description.trim() || null,
    });
    setUri('');
    setDescription('');
  };

  return (
    <Stack spacing={1.5} aria-label="Experiment artifacts">
      {artifacts.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No artifacts recorded yet.
        </Typography>
      ) : (
        <List dense disablePadding>
          {artifacts.map((artifact) => (
            <ListItem
              key={artifact.id}
              disablePadding
              sx={{ py: 0.5 }}
              secondaryAction={
                <IconButton
                  size="small"
                  aria-label={`Delete artifact ${artifact.uri}`}
                  onClick={() => onDelete(artifact.id)}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              }
            >
              <ListItemText
                primary={
                  <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
                    <Chip size="small" variant="outlined" label={artifact.artifact_type} />
                    <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                      {artifact.uri}
                    </Typography>
                  </Stack>
                }
                secondary={artifact.description}
              />
            </ListItem>
          ))}
        </List>
      )}

      <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
        <TextField
          select
          size="small"
          label="Type"
          value={artifactType}
          onChange={(event) => setArtifactType(event.target.value as ArtifactType)}
          sx={{ minWidth: 160 }}
        >
          {ARTIFACT_TYPES.map((type) => (
            <MenuItem key={type} value={type}>
              {type}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="URI / path"
          value={uri}
          onChange={(event) => setUri(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Artifact URI' } }}
          sx={{ minWidth: 220, flexGrow: 1 }}
        />
        <TextField
          size="small"
          label="Description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          slotProps={{ htmlInput: { 'aria-label': 'Artifact description' } }}
          sx={{ minWidth: 160 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={handleAdd}
          disabled={!canAdd || adding}
        >
          {adding ? 'Adding…' : 'Add Artifact'}
        </Button>
      </Stack>
    </Stack>
  );
}
