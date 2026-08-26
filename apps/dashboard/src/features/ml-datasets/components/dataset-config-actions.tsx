'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import UploadIcon from '@mui/icons-material/Upload';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { InfoTooltip } from '@/components/info-tooltip';
import { parseDatasetConfig, type DatasetConfig } from '../lib/dataset-config';

export interface DatasetConfigActionsProps {
  config: DatasetConfig;
  onImport: (config: DatasetConfig) => void;
}

/**
 * Reproducibility controls: copy the current configuration (market,
 * timeframe, range, features, targets, split) as JSON, or paste one back
 * in to restore it.
 *
 * This is purely a convenience for a person moving a configuration
 * between sessions, tabs, or teammates — it does not talk to the backend
 * and does not itself build anything. Importing only replaces this page's
 * form/selection state; the researcher still presses "Build ML Dataset"
 * themselves afterward, the same as if they had configured it by hand.
 */
export function DatasetConfigActions({ config, onImport }: DatasetConfigActionsProps) {
  const [copied, setCopied] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);

  const handleCopy = async () => {
    const text = JSON.stringify(config, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be unavailable (permissions, non-secure
      // context, jsdom in tests) — degrade to a no-op rather than throw,
      // matching `validation-issue-list.tsx`'s existing Copy Issue pattern.
    }
  };

  const handleOpenImport = () => {
    setImportText('');
    setImportError(null);
    setImportOpen(true);
  };

  const handleApplyImport = () => {
    const result = parseDatasetConfig(importText);
    if (!result.ok) {
      setImportError(result.error);
      return;
    }
    onImport(result.config);
    setImportOpen(false);
  };

  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Button
        size="small"
        variant="outlined"
        startIcon={<ContentCopyIcon fontSize="small" />}
        onClick={handleCopy}
      >
        {copied ? 'Copied!' : 'Copy Configuration'}
      </Button>
      <Button
        size="small"
        variant="outlined"
        startIcon={<UploadIcon fontSize="small" />}
        onClick={handleOpenImport}
      >
        Import Configuration
      </Button>
      <InfoTooltip
        label="Dataset configuration"
        sections={[
          {
            heading: 'Reproducibility',
            body: 'Copy captures the exact market, timeframe, range, features, targets, and split as JSON. Import restores it into the form — you still press Build ML Dataset yourself afterward.',
          },
        ]}
      />

      <Dialog open={importOpen} onClose={() => setImportOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Import Dataset Configuration</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Paste a previously copied configuration below.
            </Typography>
            <TextField
              multiline
              minRows={8}
              value={importText}
              onChange={(event) => {
                setImportText(event.target.value);
                setImportError(null);
              }}
              placeholder='{ "market": "ETHUSD", "timeframe": "1h", ... }'
              slotProps={{ htmlInput: { 'aria-label': 'Paste dataset configuration JSON' } }}
              fullWidth
            />
            {importError ? (
              <Alert severity="error" role="alert">
                {importError}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleApplyImport}
            disabled={importText.trim() === ''}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
