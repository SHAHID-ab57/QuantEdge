'use client';

import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import type {
  ValidationRule,
  ValidationRuleCatalog as ValidationRuleCatalogData,
} from '@/types/api/dataset-validation';
import { ruleKnowledgeFor } from '../lib/rule-knowledge';

export interface ValidationRuleCatalogProps {
  catalogue: ValidationRuleCatalogData | undefined;
  loading: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  structural: 'Structural',
  data_quality: 'Data Quality',
  time_series: 'Time-Series',
  feature: 'Feature',
};

const SEVERITY_COLOR = {
  error: 'error',
  warning: 'warning',
  info: 'info',
} as const;

function RuleRow({ rule }: { rule: ValidationRule }) {
  const [expanded, setExpanded] = useState(false);
  const knowledge = ruleKnowledgeFor(rule.name);

  return (
    <ListItem disablePadding sx={{ display: 'block' }}>
      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ py: 0.25 }}>
        <IconButton
          size="small"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? `Collapse ${rule.name}` : `Expand ${rule.name}`}
          aria-expanded={expanded}
        >
          {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        </IconButton>
        <ListItemText
          primary={
            <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap">
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {rule.name}
              </Typography>
              <Chip
                size="small"
                variant="outlined"
                color={SEVERITY_COLOR[rule.default_severity]}
                label={rule.default_severity}
              />
            </Stack>
          }
          secondary={rule.description}
          slotProps={{ secondary: { noWrap: true, variant: 'caption' } }}
          sx={{ my: 0 }}
        />
      </Stack>
      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ pl: 5, pr: 1, pb: 1 }}>
          <Stack spacing={0.75}>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Why it matters:
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {knowledge.whyItMatters}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={0.5}>
              <Typography variant="caption" sx={{ fontWeight: 700 }}>
                Example failure:
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {knowledge.exampleFailure}
              </Typography>
            </Stack>
          </Stack>
        </Box>
      </Collapse>
    </ListItem>
  );
}

function CatalogSkeleton() {
  return (
    <Stack spacing={1} role="status" aria-label="Loading validation rule catalogue">
      {[0, 1, 2].map((key) => (
        <Skeleton key={key} variant="rounded" height={32} />
      ))}
    </Stack>
  );
}

/**
 * The registered rule catalogue, grouped by category — read straight from
 * `GET /validation/rules`, so a rule added to the backend's
 * `app/dataset_validation/rules/` appears here with no frontend change,
 * the same extensibility guarantee the Feature Selector's own catalogue
 * already gives generators. Shown so a researcher knows what the engine
 * checks *before* running it, not only after.
 *
 * Each rule expands to show curated "Why it matters" / "Example failure"
 * content (`rule-knowledge.ts`) alongside its API-provided name, category,
 * description, and default severity — the same curated-plus-honest-
 * fallback pattern `indicator-knowledge.ts` already established for
 * indicators, applied here so an uncurated future rule still renders a
 * complete, non-broken panel rather than a blank one.
 */
export function ValidationRuleCatalog({ catalogue, loading }: ValidationRuleCatalogProps) {
  if (loading) {
    return <CatalogSkeleton />;
  }
  if (!catalogue) {
    return null;
  }

  const grouped = catalogue.categories.map((category) => ({
    category,
    rules: catalogue.rules.filter((rule) => rule.category === category),
  }));

  return (
    <Stack spacing={0.5} aria-label="Available validation rules">
      <Typography variant="caption" color="text.secondary">
        {catalogue.total} checks across {catalogue.categories.length} categories run by default.
      </Typography>
      <List dense disablePadding subheader={<li />}>
        {grouped.map(({ category, rules }) => (
          <li key={category}>
            <ul style={{ padding: 0 }}>
              <ListSubheader disableSticky sx={{ lineHeight: 2.25, bgcolor: 'transparent' }}>
                {CATEGORY_LABELS[category] ?? category}
              </ListSubheader>
              {rules.map((rule) => (
                <RuleRow key={rule.name} rule={rule} />
              ))}
            </ul>
          </li>
        ))}
      </List>
    </Stack>
  );
}
