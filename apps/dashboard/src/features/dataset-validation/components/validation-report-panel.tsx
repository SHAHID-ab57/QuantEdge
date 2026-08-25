'use client';

import FileDownloadIcon from '@mui/icons-material/FileDownload';
import SearchIcon from '@mui/icons-material/Search';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMemo, useState } from 'react';
import { downloadBlob } from '@/lib/download-file';
import type { ValidationIssue, ValidationReport } from '@/types/api/dataset-validation';
import { ValidationIssueList } from './validation-issue-list';

export interface ValidationReportPanelProps {
  report: ValidationReport;
}

type Severity = ValidationIssue['severity'];

const ALL_SEVERITIES: readonly Severity[] = ['error', 'warning', 'info'];
const ALL_CATEGORIES = '__all__';

const SEVERITY_COLOR = {
  error: 'error',
  warning: 'warning',
  info: 'info',
} as const;

const CATEGORY_LABELS: Record<string, string> = {
  structural: 'Structural',
  data_quality: 'Data Quality',
  time_series: 'Time-Series',
  feature: 'Feature',
};

function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

function matchesSearch(issue: ValidationIssue, needle: string): boolean {
  if (!needle) {
    return true;
  }
  const haystack =
    `${issue.rule} ${issue.code} ${issue.message} ${issue.column ?? ''}`.toLowerCase();
  return haystack.includes(needle);
}

function issuesFilename(report: ValidationReport): string {
  const safe = (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, '-');
  const stamp = report.validated_at.replace(/[^0-9]/g, '').slice(0, 14);
  return `${safe(report.symbol)}-${safe(report.timeframe)}-issues-${stamp}.json`;
}

/**
 * Every finding from one validation run, with the tools a researcher needs
 * to work through a large report quickly: full-text search, a severity
 * filter (multi-select — error/warning/info can each be toggled off),
 * a category filter, and a bulk Expand All/Collapse All alongside each
 * row's own expand toggle (see `ValidationIssueList`). "Export Issues"
 * downloads only the *currently filtered* issues as JSON — a narrower,
 * more focused artifact than the full report `ValidationReportDownload`
 * already offers.
 *
 * All filtering runs through a single `useMemo`, so typing in the search
 * box or toggling a severity chip never re-filters more than once per
 * change, keeping this responsive over a report with a large issue count.
 */
export function ValidationReportPanel({ report }: ValidationReportPanelProps) {
  const [search, setSearch] = useState('');
  const [severities, setSeverities] = useState<ReadonlySet<Severity>>(new Set(ALL_SEVERITIES));
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [expandSignal, setExpandSignal] = useState<{ key: number; expanded: boolean }>({
    key: 0,
    expanded: false,
  });

  const categories = useMemo(
    () => Array.from(new Set(report.issues.map((issue) => issue.category))).sort(),
    [report.issues],
  );

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return report.issues.filter(
      (issue) =>
        severities.has(issue.severity) &&
        (category === ALL_CATEGORIES || issue.category === category) &&
        matchesSearch(issue, needle),
    );
  }, [report.issues, search, severities, category]);

  const toggleSeverity = (severity: Severity) => {
    setSeverities((current) => {
      const next = new Set(current);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  };

  const exportIssues = () => {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], {
      type: 'application/json',
    });
    downloadBlob(blob, issuesFilename(report));
  };

  const setExpandAll = (expanded: boolean) => {
    setExpandSignal((current) => ({ key: current.key + 1, expanded }));
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <TextField
          size="small"
          placeholder="Search issues…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          sx={{ flex: 1, minWidth: 200 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
            htmlInput: { 'aria-label': 'Search issues' },
          }}
        />
        <TextField
          select
          label="Category"
          size="small"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value={ALL_CATEGORIES}>All categories</MenuItem>
          {categories.map((entry) => (
            <MenuItem key={entry} value={entry}>
              {categoryLabel(entry)}
            </MenuItem>
          ))}
        </TextField>
        <Button
          size="small"
          startIcon={<FileDownloadIcon />}
          onClick={exportIssues}
          disabled={filtered.length === 0}
          aria-label="Export filtered issues as JSON"
        >
          Export Issues
        </Button>
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Stack direction="row" spacing={0.5} role="group" aria-label="Filter by severity">
          {ALL_SEVERITIES.map((severity) => {
            const active = severities.has(severity);
            return (
              <Chip
                key={severity}
                label={severity}
                size="small"
                clickable
                onClick={() => toggleSeverity(severity)}
                color={active ? SEVERITY_COLOR[severity] : 'default'}
                variant={active ? 'filled' : 'outlined'}
                aria-pressed={active}
              />
            );
          })}
        </Stack>
        <Button size="small" onClick={() => setExpandAll(true)}>
          Expand All
        </Button>
        <Button size="small" onClick={() => setExpandAll(false)}>
          Collapse All
        </Button>
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Showing {filtered.length} of {report.issues.length} issue
        {report.issues.length === 1 ? '' : 's'}
      </Typography>

      <ValidationIssueList
        key={expandSignal.key}
        issues={filtered}
        defaultExpanded={expandSignal.expanded}
        emptyMessage={
          report.issues.length === 0
            ? 'No issues — every structural, data-quality, time-series, and feature check passed.'
            : 'No issues match the current filters.'
        }
      />
    </Stack>
  );
}
