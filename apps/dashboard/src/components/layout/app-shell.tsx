'use client';

import { useMediaQuery, useTheme } from '@mui/material';
import Box from '@mui/material/Box';
import Toolbar from '@mui/material/Toolbar';
import { useUiStore } from '@/store/ui-store';
import { Sidebar } from './sidebar';
import { TopBar } from './top-bar';

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const toggleCollapsed = useUiStore((state) => state.toggleCollapsed);

  const handleMenuClick = () => {
    if (mobile) {
      toggleSidebar();
    } else {
      toggleCollapsed();
    }
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100dvh' }}>
      <TopBar mobile={mobile} onMenuClick={handleMenuClick} />
      <Sidebar mobile={mobile} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          px: { xs: 2, md: 3 },
          py: 3,
        }}
      >
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
}
