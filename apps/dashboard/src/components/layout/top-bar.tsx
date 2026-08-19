'use client';

import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import MenuIcon from '@mui/icons-material/Menu';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';

export function TopBar({
  mobile,
  onMenuClick,
}: Readonly<{ mobile: boolean; onMenuClick: () => void }>) {
  return (
    <AppBar
      position="fixed"
      color="transparent"
      elevation={0}
      sx={{
        borderBottom: 1,
        borderColor: 'divider',
        backdropFilter: 'blur(8px)',
        backgroundColor: 'rgba(10, 14, 23, 0.8)',
      }}
    >
      <Toolbar>
        <IconButton
          edge="start"
          color="inherit"
          aria-label={mobile ? 'Open navigation' : 'Toggle sidebar'}
          onClick={onMenuClick}
          sx={{ mr: 2 }}
        >
          <MenuIcon />
        </IconButton>
        <Typography variant="h6" noWrap sx={{ fontWeight: 600 }}>
          {mobile ? 'Research Dashboard' : ''}
        </Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Box id="topbar-actions" />
      </Toolbar>
    </AppBar>
  );
}
