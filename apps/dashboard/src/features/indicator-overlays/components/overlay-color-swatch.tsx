'use client';

import CheckIcon from '@mui/icons-material/Check';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Tooltip from '@mui/material/Tooltip';
import { useTheme } from '@mui/material/styles';
import { memo, useState, type MouseEvent } from 'react';
import { overlayColorPalette } from '@/components/chart/overlay-colors';

export interface OverlayColorSwatchProps {
  /** The overlay's currently-resolved color (auto-assigned or overridden). */
  color: string;
  /** Names the overlay this swatch belongs to, for the button's accessible name. */
  label: string;
  /** Whether the current color is a manual override (shown as the checked entry in the picker). */
  isOverride: boolean;
  onSelect: (color: string) => void;
  onReset: () => void;
}

/**
 * The overlay color dot, promoted from a static `<Box>` into an
 * interactive control: click it to open a small palette and pick a manual
 * color for this overlay, overriding the automatic rotation
 * (`resolveOverlayColor`) without disturbing any other overlay's color.
 * Shared by `IndicatorPanel`'s overlay rows and `IndicatorLegend`'s
 * entries — one implementation, so customizing a color from either
 * surface behaves identically.
 */
function OverlayColorSwatchInner({
  color,
  label,
  isOverride,
  onSelect,
  onReset,
}: OverlayColorSwatchProps) {
  const theme = useTheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const palette = overlayColorPalette(theme);

  const close = () => setAnchor(null);

  return (
    <>
      <Tooltip title={`Change ${label}'s color`}>
        <Box
          component="button"
          type="button"
          onClick={(event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget)}
          aria-label={`Change ${label}'s color`}
          aria-haspopup="menu"
          sx={{
            width: 12,
            height: 12,
            borderRadius: '50%',
            bgcolor: color,
            flexShrink: 0,
            p: 0,
            border: 'none',
            cursor: 'pointer',
            outlineOffset: 2,
          }}
        />
      </Tooltip>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={close}>
        {palette.map((swatch) => (
          <MenuItem
            key={swatch.key}
            onClick={() => {
              onSelect(swatch.color);
              close();
            }}
          >
            <ListItemIcon>
              <Box
                sx={{
                  width: 14,
                  height: 14,
                  borderRadius: '50%',
                  bgcolor: swatch.color,
                }}
              />
            </ListItemIcon>
            <ListItemText sx={{ textTransform: 'capitalize' }}>{swatch.key}</ListItemText>
            {swatch.color === color ? <CheckIcon fontSize="small" /> : null}
          </MenuItem>
        ))}
        <Divider />
        <MenuItem
          disabled={!isOverride}
          onClick={() => {
            onReset();
            close();
          }}
        >
          <ListItemIcon>
            <RestartAltIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Reset to automatic</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}

export const OverlayColorSwatch = memo(OverlayColorSwatchInner);
