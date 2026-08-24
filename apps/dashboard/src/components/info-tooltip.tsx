'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { memo } from 'react';

export interface InfoTooltipSection {
  heading: string;
  body: string;
}

export interface InfoTooltipProps {
  /** Names the thing being explained; becomes the button's accessible name ("About {label}"). */
  label: string;
  sections: InfoTooltipSection[];
  maxWidth?: number;
}

/**
 * The ⓘ affordance that sits beside a field or figure needing a short
 * explanation — promoted out of the Trade Analytics dashboard's
 * `MetricInfo` once the Technical Indicators page needed the identical
 * pattern for a different set of things to explain. `MetricInfo` now
 * delegates here so the one accessibility contract lives in one place.
 *
 * Accessibility notes, since a tooltip on an icon is easy to get wrong:
 *
 * - It's a real `IconButton`, so it is in the tab order and reachable
 *   without a mouse. MUI's `Tooltip` opens on focus as well as hover, so a
 *   keyboard user gets the same explanation a mouse user does.
 * - The icon itself is `aria-hidden`; the button carries an explicit
 *   `aria-label` naming the thing being explained, so a screen reader
 *   announces which field is being explained rather than a bare "info
 *   button" repeated throughout the page.
 * - The tooltip body gets `role="tooltip"` and is wired to the button via
 *   `aria-describedby` (MUI does this automatically when open), so the
 *   explanation is announced as a description of the button.
 * - `enterTouchDelay={0}` makes it usable on touch, where there is no
 *   hover state to rely on at all.
 */
function InfoTooltipInner({ label, sections, maxWidth = 300 }: InfoTooltipProps) {
  return (
    <Tooltip
      arrow
      enterTouchDelay={0}
      leaveTouchDelay={8_000}
      title={
        <Box sx={{ maxWidth, py: 0.5 }}>
          {sections.map((section) => (
            <Box key={section.heading} sx={{ '& + &': { mt: 1 } }}>
              <Typography
                variant="caption"
                component="p"
                sx={{
                  fontWeight: 700,
                  letterSpacing: 0.4,
                  textTransform: 'uppercase',
                  opacity: 0.75,
                }}
              >
                {section.heading}
              </Typography>
              <Typography
                variant="caption"
                component="p"
                sx={{ lineHeight: 1.5, whiteSpace: 'pre-line' }}
              >
                {section.body}
              </Typography>
            </Box>
          ))}
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

export const InfoTooltip = memo(InfoTooltipInner);
