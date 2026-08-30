'use client';

import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { FeatureLineage } from '@/types/api/features';

export interface FeatureLineagePanelProps {
  lineage: FeatureLineage;
}

function ChipList({ label, names }: { label: string; names: string[] }) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 80 }}>
        {label}
      </Typography>
      {names.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          none
        </Typography>
      ) : (
        names.map((name) => <Chip key={name} size="small" variant="outlined" label={name} />)
      )}
    </Stack>
  );
}

/**
 * The whole feature registry's dependency graph — every generator's direct
 * and transitive dependencies/dependents, plus the order they would need
 * to be computed in.
 *
 * Rendered as a grouped list of chips rather than a drawn graph (nodes and
 * edges, force-directed or otherwise): this platform has no graph-drawing
 * library today, and every registered generator declares zero dependencies
 * as of this writing (see `FeatureMetadata.dependencies`'s own docstring) —
 * building an interactive node-link visualization for a graph that is
 * currently edgeless would be speculative complexity with nothing to show.
 * This view is fully correct and immediately useful the day a real
 * dependency is declared: `dependencies`/`depended_on_by` populate and
 * render exactly as they would for any other feature, no code change here.
 */
export function FeatureLineagePanel({ lineage }: FeatureLineagePanelProps) {
  if (lineage.nodes.length === 0) return null;

  return (
    <Stack spacing={1.5} aria-label="Feature dependency graph">
      {lineage.edges.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          No registered feature declares a dependency on another today — every node below is
          independent.
        </Typography>
      ) : null}

      <Stack spacing={1}>
        {lineage.nodes.map((node) => (
          <Stack key={node.name} spacing={0.25} sx={{ pb: 0.5 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {node.label}
              </Typography>
              <Chip size="small" label={node.category} />
            </Stack>
            <ChipList label="Depends on" names={[...node.dependencies]} />
            <ChipList label="Used by" names={[...node.depended_on_by]} />
          </Stack>
        ))}
      </Stack>

      <Typography variant="caption" color="text.secondary">
        Computation order: {lineage.topological_order.join(' → ')}
      </Typography>
    </Stack>
  );
}
