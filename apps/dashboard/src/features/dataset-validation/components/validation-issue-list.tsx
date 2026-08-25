'use client';

import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DoneIcon from '@mui/icons-material/Done';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import type { ValidationIssue } from '@/types/api/dataset-validation';
import { suggestedFixFor } from '../lib/rule-knowledge';

export interface ValidationIssueListProps {
  /** Already filtered/searched by the caller — this component only renders. */
  issues: ValidationIssue[];
  emptyMessage: string;
  /** Initial expand state for every row — used by `ValidationReportPanel`'s Expand All/Collapse All. */
  defaultExpanded?: boolean;
}

const SEVERITY_COLOR = {
  error: 'error',
  warning: 'warning',
  info: 'info',
} as const;

function issueDetail(issue: ValidationIssue): string {
  const parts: string[] = [];
  if (issue.column) {
    parts.push(`column: ${issue.column}`);
  }
  if (issue.row_index !== null && issue.row_index !== undefined) {
    parts.push(`row: ${issue.row_index}`);
  }
  if (issue.count !== null && issue.count !== undefined) {
    parts.push(`count: ${issue.count.toLocaleString()}`);
  }
  return parts.join(' · ');
}

function copyText(issue: ValidationIssue): string {
  const lines = [
    `Rule: ${issue.rule}`,
    `Severity: ${issue.severity}`,
    `Code: ${issue.code}`,
    `Message: ${issue.message}`,
  ];
  if (issue.column) lines.push(`Affected column: ${issue.column}`);
  if (issue.row_index !== null && issue.row_index !== undefined) {
    lines.push(`Affected row: ${issue.row_index}`);
  }
  if (issue.count !== null && issue.count !== undefined) {
    lines.push(`Count: ${issue.count}`);
  }
  lines.push(`Suggested fix: ${suggestedFixFor(issue.code)}`);
  return lines.join('\n');
}

function CopyIssueButton({ issue }: { issue: ValidationIssue }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(copyText(issue));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied or unavailable (e.g. an insecure
      // context, or a browser permission refusal) — the button simply
      // doesn't confirm success rather than throwing in the UI.
    }
  };

  return (
    <IconButton
      size="small"
      onClick={handleCopy}
      aria-label={`Copy issue: ${issue.code}`}
      title="Copy issue"
    >
      {copied ? (
        <DoneIcon fontSize="small" color="success" />
      ) : (
        <ContentCopyIcon fontSize="small" />
      )}
    </IconButton>
  );
}

function IssueRow({
  issue,
  defaultExpanded = false,
}: {
  issue: ValidationIssue;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      <Stack direction="row" spacing={0.5} alignItems="flex-start" sx={{ py: 0.75 }}>
        <IconButton
          size="small"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? `Collapse issue: ${issue.code}` : `Expand issue: ${issue.code}`}
          aria-expanded={expanded}
        >
          {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        </IconButton>
        <ListItemText
          primary={
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Chip
                size="small"
                color={SEVERITY_COLOR[issue.severity]}
                variant="outlined"
                label={issue.code}
              />
              <Chip size="small" variant="outlined" label={issue.category} />
            </Stack>
          }
          secondary={
            <>
              <Typography component="span" variant="body2" display="block">
                {issue.message}
              </Typography>
              {issueDetail(issue) ? (
                <Typography
                  component="span"
                  variant="caption"
                  color="text.secondary"
                  display="block"
                >
                  {issueDetail(issue)} · rule: {issue.rule}
                </Typography>
              ) : (
                <Typography component="span" variant="caption" color="text.secondary">
                  rule: {issue.rule}
                </Typography>
              )}
            </>
          }
          sx={{ my: 0 }}
        />
        <CopyIssueButton issue={issue} />
      </Stack>
      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ pl: 5, pr: 1, pb: 1 }}>
          <Stack spacing={0.5}>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Affected column:
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {issue.column ?? '—'}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Affected row:
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {issue.row_index ?? '—'}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Suggested fix:
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {suggestedFixFor(issue.code)}
              </Typography>
            </Stack>
          </Stack>
        </Box>
      </Collapse>
    </ListItem>
  );
}

/**
 * Renders an already-filtered array of issues — search, severity, and
 * category filtering all live one level up, in `ValidationReportPanel`.
 * Each row shows its rule/severity/message/affected-column-or-row at a
 * glance, and expands to show a suggested next step
 * (`suggestedFixFor`, keyed by the issue's own `code` since one rule can
 * emit more than one distinct code) without leaving the report.
 */
export function ValidationIssueList({
  issues,
  emptyMessage,
  defaultExpanded = false,
}: ValidationIssueListProps) {
  if (issues.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" role="status">
        {emptyMessage}
      </Typography>
    );
  }

  return (
    <List dense aria-label="Validation issues" sx={{ py: 0 }}>
      {issues.map((issue, index) => (
        <IssueRow
          key={`${issue.rule}-${issue.code}-${index}`}
          issue={issue}
          defaultExpanded={defaultExpanded}
        />
      ))}
    </List>
  );
}
