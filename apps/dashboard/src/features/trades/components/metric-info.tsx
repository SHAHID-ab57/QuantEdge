'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo } from 'react';
import { METRIC_HELP, type MetricKey } from '../lib/metric-help';

export interface MetricInfoProps {
  metric: MetricKey;
  /** Human-readable metric name, used in the button's accessible name. */
  label: string;
}

interface HelpSectionProps {
  heading: string;
  body: string;
}

function HelpSection({ heading, body }: HelpSectionProps) {
  return (
    <Box sx={{ '& + &': { mt: 1 } }}>
      <Typography
        variant="caption"
        component="p"
        sx={{ fontWeight: 700, letterSpacing: 0.4, textTransform: 'uppercase', opacity: 0.75 }}
      >
        {heading}
      </Typography>
      <Typography variant="caption" component="p" sx={{ lineHeight: 1.5 }}>
        {body}
      </Typography>
    </Box>
  );
}

/**
 * The Info affordance that sits beside every metric on this dashboard,
 * explaining what it means, why it matters, how it's calculated, and how to
 * read a typical value — sourced from one shared dictionary
 * (`lib/metric-help.ts`) so no two panels can explain the same metric
 * differently.
 *
 * Accessibility notes, since a tooltip on an icon is easy to get wrong:
 *
 * - It's a real `IconButton`, so it is in the tab order and reachable
 *   without a mouse. MUI's `Tooltip` opens on focus as well as hover, so a
 *   keyboard user gets the same explanation a mouse user does.
 * - The icon itself is `aria-hidden`; the button carries an explicit
 *   `aria-label` naming the metric ("About Session VWAP"), so a screen
 *   reader announces which metric is being explained rather than a bare
 *   "info button" repeated a dozen times down the page.
 * - The tooltip body is given `role="tooltip"` and wired to the button via
 *   `aria-describedby` (MUI does this automatically when the tooltip is
 *   open), so the explanation is announced as a description of the button
 *   rather than as orphaned text.
 * - `enterTouchDelay={0}` makes it usable on touch, where there is no hover
 *   state to rely on at all.
 */
function MetricInfoInner({ metric, label }: MetricInfoProps) {
  const help = METRIC_HELP[metric];
  return (
    <Tooltip
      arrow
      enterTouchDelay={0}
      leaveTouchDelay={8_000}
      title={
        <Box sx={{ maxWidth: 300, py: 0.5 }}>
          <HelpSection heading="What it is" body={help.what} />
          <HelpSection heading="Why it matters" body={help.why} />
          {'how' in help && help.how ? (
            <HelpSection heading="How it's calculated" body={help.how} />
          ) : null}
          <HelpSection heading="How to read it" body={help.interpretation} />
        </Box>
      }
    >
      <IconButton
        size="small"
        aria-label={`About ${label}`}
        sx={{
          p: 0.25,
          color: 'text.disabled',
          transition: 'color 150ms ease',
          '&:hover, &:focus-visible': { color: 'info.main' },
        }}
      >
        <InfoOutlinedIcon sx={{ fontSize: 14 }} aria-hidden />
      </IconButton>
    </Tooltip>
  );
}

export const MetricInfo = memo(MetricInfoInner);
