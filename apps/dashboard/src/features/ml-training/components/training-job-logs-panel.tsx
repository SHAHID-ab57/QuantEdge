'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DownloadIcon from '@mui/icons-material/Download';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import SearchIcon from '@mui/icons-material/Search';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useEffect, useMemo, useRef, useState } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { TrainingJobLog, TrainingJobStatus } from '@/types/api/training';
import { stageLabel } from '../lib/training-job-status';

export interface TrainingJobLogsPanelProps {
  jobId: string;
  logs: TrainingJobLog[];
  status: TrainingJobStatus;
}

const LOG_LEVEL_COLOR: Record<string, 'default' | 'info' | 'warning' | 'error'> = {
  debug: 'default',
  info: 'info',
  warning: 'warning',
  error: 'error',
};

function formatLogTimestamp(value: string): string {
  return new Date(value).toLocaleTimeString();
}

function logsToText(logs: TrainingJobLog[]): string {
  return logs
    .map((log) => {
      const stage = log.stage ? `[${stageLabel(log.stage)}] ` : '';
      return `${new Date(log.logged_at).toISOString()} ${log.level.toUpperCase()} ${stage}${log.message}`;
    })
    .join('\n');
}

function CopyLogsButton({ logs }: { logs: TrainingJobLog[] }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(logsToText(logs));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied or unavailable — the button simply
      // doesn't confirm success rather than throwing in the UI.
    }
  };

  return (
    <Tooltip title={copied ? 'Copied' : 'Copy logs'}>
      <span>
        <IconButton
          size="small"
          aria-label="Copy logs"
          onClick={handleCopy}
          disabled={logs.length === 0}
        >
          <ContentCopyIcon fontSize="small" />
        </IconButton>
      </span>
    </Tooltip>
  );
}

/**
 * The job's full log trail, upgraded from a bare scrolling list: a
 * timestamp and a stage `Chip` per line, search-to-filter, copy/download
 * of the full (unfiltered) trail, collapse/expand to reclaim space once a
 * job is well understood, and auto-scroll to the newest line while the
 * job is actively running (a status monitor watching a live run should not
 * have to manually scroll to see what just happened).
 */
export function TrainingJobLogsPanel({ jobId, logs, status }: TrainingJobLogsPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [search, setSearch] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  const filteredLogs = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return logs;
    return logs.filter(
      (log) =>
        log.message.toLowerCase().includes(query) ||
        (log.stage ?? '').toLowerCase().includes(query) ||
        log.level.toLowerCase().includes(query),
    );
  }, [logs, search]);

  useEffect(() => {
    if (status === 'running' && expanded && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [logs.length, status, expanded]);

  const handleDownload = () => {
    const blob = new Blob([logsToText(logs)], { type: 'text/plain;charset=utf-8' });
    downloadBlob(blob, `training-job-${jobId}.log`);
  };

  return (
    <Stack spacing={0.5}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <IconButton
            size="small"
            aria-label={expanded ? 'Collapse logs' : 'Expand logs'}
            aria-expanded={expanded}
            onClick={() => setExpanded((prev) => !prev)}
          >
            {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
          <Typography variant="subtitle2">Logs ({logs.length})</Typography>
        </Stack>
        <Stack direction="row" spacing={0.5}>
          <CopyLogsButton logs={logs} />
          <Tooltip title="Download logs">
            <span>
              <IconButton
                size="small"
                aria-label="Download logs"
                onClick={handleDownload}
                disabled={logs.length === 0}
              >
                <DownloadIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>
      <Collapse in={expanded} unmountOnExit>
        <Stack spacing={0.75}>
          {logs.length > 0 ? (
            <TextField
              size="small"
              placeholder="Search logs"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon fontSize="small" />
                    </InputAdornment>
                  ),
                },
                htmlInput: { 'aria-label': 'Search logs' },
              }}
            />
          ) : null}
          {logs.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No logs yet — run the job to execute the pipeline.
            </Typography>
          ) : (
            <Stack
              ref={listRef}
              spacing={0.5}
              sx={{ maxHeight: 240, overflowY: 'auto' }}
              role="log"
              aria-label="Training job logs"
              aria-live="polite"
            >
              {filteredLogs.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No log lines match &quot;{search}&quot;.
                </Typography>
              ) : (
                filteredLogs.map((log) => (
                  <Stack key={log.id} direction="row" spacing={1} alignItems="flex-start">
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ minWidth: 72, fontVariantNumeric: 'tabular-nums' }}
                    >
                      {formatLogTimestamp(log.logged_at)}
                    </Typography>
                    <Chip
                      size="small"
                      label={log.level}
                      color={LOG_LEVEL_COLOR[log.level] ?? 'default'}
                      sx={{ minWidth: 64 }}
                    />
                    {log.stage ? (
                      <Chip size="small" variant="outlined" label={stageLabel(log.stage)} />
                    ) : null}
                    <Typography variant="caption" sx={{ flex: 1 }}>
                      {log.message}
                    </Typography>
                  </Stack>
                ))
              )}
            </Stack>
          )}
        </Stack>
      </Collapse>
    </Stack>
  );
}
