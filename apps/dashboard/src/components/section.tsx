'use client';

import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

export interface SectionProps {
  title: string;
  /** One short line under the title, for scope or caveats ("last minute", "since connecting"). */
  subtitle?: string;
  /** Rendered at the right of the header row — filters, selectors, export buttons. */
  action?: ReactNode;
  children: ReactNode;
}

/**
 * One titled group of related panels. Originally written for the Live
 * Trade Analytics dashboard to replace a flat run of sibling `Paper`s
 * separated by `Divider`s and bare `overline` labels, which spent a lot of
 * vertical space on separators and left every metric at the same visual
 * weight regardless of importance. Promoted here once the Replay engine
 * needed the identical grouping pattern, rather than a second local copy.
 *
 * A section is a single bordered surface with its heading built in, so
 * related metrics read as one block, and the gap *between* sections
 * (rather than a rule plus two margins) is what separates them. Its own
 * `<section aria-labelledby>` wiring means a screen reader can navigate
 * the page by landmark and hear the group name.
 */
export function Section({ title, subtitle, action, children }: SectionProps) {
  const headingId = `section-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return (
    <Paper
      component="section"
      aria-labelledby={headingId}
      variant="outlined"
      sx={{
        p: { xs: 1.5, sm: 2 },
        borderColor: 'divider',
        backgroundImage: 'none',
        transition: 'border-color 200ms ease',
        '&:hover': { borderColor: 'rgba(148, 163, 184, 0.28)' },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        useFlexGap
        spacing={1}
        sx={{ mb: 1.5 }}
      >
        <Box>
          <Typography
            id={headingId}
            variant="subtitle2"
            component="h2"
            sx={{ fontWeight: 700, letterSpacing: 0.3 }}
          >
            {title}
          </Typography>
          {subtitle ? (
            <Typography variant="caption" color="text.secondary">
              {subtitle}
            </Typography>
          ) : null}
        </Box>
        {action}
      </Stack>
      {children}
    </Paper>
  );
}
