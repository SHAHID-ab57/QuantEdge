'use client';

import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo, useState } from 'react';
import type { Indicator } from '@/types/api/indicators';
import { getIndicatorKnowledge } from '../lib/indicator-knowledge';

export interface IndicatorInfoPanelProps {
  indicator: Indicator;
  /** Expanded by default the first time an indicator is picked; the researcher's own toggle wins after that. */
  defaultExpanded?: boolean;
}

interface SectionProps {
  heading: string;
  children: React.ReactNode;
}

function InfoSection({ heading, children }: SectionProps) {
  return (
    <Box>
      <Typography
        variant="caption"
        component="h4"
        sx={{ fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', opacity: 0.75 }}
      >
        {heading}
      </Typography>
      {children}
    </Box>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        Not yet documented for this indicator.
      </Typography>
    );
  }
  return (
    <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
      {items.map((item) => (
        <Typography key={item} component="li" variant="body2">
          {item}
        </Typography>
      ))}
    </Box>
  );
}

/**
 * A dedicated research panel replacing the previous one-line description —
 * category, purpose, the math intuition, the formula, recommended
 * parameter values, advantages/limitations, use cases, interpretation
 * guidance, and a methodology reference, all sourced from
 * `indicator-knowledge.ts`.
 *
 * Collapsible via MUI's `Accordion` rather than a hand-rolled disclosure —
 * expand/collapse, `aria-expanded`, and keyboard activation all come from
 * the same component this codebase already uses elsewhere, so no new
 * accessibility surface is introduced for this page alone.
 */
function IndicatorInfoPanelInner({ indicator, defaultExpanded = true }: IndicatorInfoPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const knowledge = getIndicatorKnowledge(indicator);

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, next) => setExpanded(next)}
      disableGutters
      variant="outlined"
      sx={{ '&:before': { display: 'none' } }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-controls="indicator-info-content">
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 700 }}>
            {indicator.label}
          </Typography>
          <Chip label={indicator.category} size="small" color="primary" variant="outlined" />
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={2}>
          <InfoSection heading="Purpose">
            <Typography variant="body2">{knowledge.purpose}</Typography>
          </InfoSection>

          <InfoSection heading="Mathematical intuition">
            <Typography variant="body2">{knowledge.mathIntuition}</Typography>
          </InfoSection>

          <InfoSection heading="Formula">
            <Typography
              variant="body2"
              component="code"
              sx={{
                display: 'block',
                fontFamily: 'monospace',
                bgcolor: 'action.hover',
                borderRadius: 1,
                p: 1,
                overflowX: 'auto',
              }}
            >
              {knowledge.formula}
            </Typography>
          </InfoSection>

          <InfoSection heading="Recommended parameter values">
            {Object.keys(knowledge.parameters).length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Not yet documented for this indicator.
              </Typography>
            ) : (
              <Stack spacing={0.5}>
                {Object.entries(knowledge.parameters).map(([name, parameter]) => (
                  <Typography key={name} variant="body2">
                    <strong>{name}:</strong>{' '}
                    {parameter.recommended && parameter.recommended.length > 0
                      ? parameter.recommended.join(', ')
                      : 'no common presets documented'}
                  </Typography>
                ))}
              </Stack>
            )}
          </InfoSection>

          <InfoSection heading="Advantages">
            <BulletList items={knowledge.advantages} />
          </InfoSection>

          <InfoSection heading="Limitations">
            <BulletList items={knowledge.limitations} />
          </InfoSection>

          <InfoSection heading="Typical use cases">
            <BulletList items={knowledge.useCases} />
          </InfoSection>

          <InfoSection heading="Common interpretation">
            <Typography variant="body2">{knowledge.interpretation}</Typography>
          </InfoSection>

          {knowledge.methodology ? (
            <InfoSection heading="Methodology reference">
              <Typography variant="body2" color="text.secondary">
                {knowledge.methodology}
              </Typography>
            </InfoSection>
          ) : null}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}

export const IndicatorInfoPanel = memo(IndicatorInfoPanelInner);
