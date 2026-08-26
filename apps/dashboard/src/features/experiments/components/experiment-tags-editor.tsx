'use client';

import Autocomplete from '@mui/material/Autocomplete';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

export interface ExperimentTagsEditorProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
}

/**
 * An always-editable tag list (unlike Notes, which toggles into an edit
 * mode) — a tag is a short, low-stakes label, so committing on every
 * add/remove reads naturally as "tags are just always live," matching how
 * the create-experiment dialog's own tag input already behaves.
 */
export function ExperimentTagsEditor({
  tags,
  onChange,
  disabled = false,
}: ExperimentTagsEditorProps) {
  return (
    <Stack spacing={1} aria-label="Experiment tags">
      <Typography variant="caption" color="text.secondary">
        Tags
      </Typography>
      <Autocomplete
        multiple
        freeSolo
        options={[]}
        value={tags}
        disabled={disabled}
        onChange={(_, next) => onChange(next as string[])}
        renderTags={(value, getTagProps) =>
          value.map((tag, index) => (
            <Chip size="small" label={tag} {...getTagProps({ index })} key={tag} />
          ))
        }
        renderInput={(params) => (
          <TextField
            {...params}
            placeholder={tags.length === 0 ? 'Type a tag and press Enter' : undefined}
            slotProps={{ htmlInput: { ...params.inputProps, 'aria-label': 'Tags' } }}
          />
        )}
      />
    </Stack>
  );
}
