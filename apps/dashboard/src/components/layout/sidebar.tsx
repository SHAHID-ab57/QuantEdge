'use client';

import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import { useUiStore } from '@/store/ui-store';
import { SidebarNav } from './sidebar-nav';

const DRAWER_WIDTH = 240;
const DRAWER_WIDTH_COLLAPSED = 64;
const MOBILE_DRAWER_WIDTH = 280;

export function Sidebar({ mobile }: Readonly<{ mobile: boolean }>) {
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);
  const closeSidebar = useUiStore((state) => state.closeSidebar);
  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);

  if (mobile) {
    return (
      <Drawer
        variant="temporary"
        open={sidebarOpen}
        onClose={closeSidebar}
        ModalProps={{ keepMounted: true }}
        sx={{
          '& .MuiDrawer-paper': {
            width: MOBILE_DRAWER_WIDTH,
          },
        }}
      >
        <Toolbar>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            Research Dashboard
          </Typography>
        </Toolbar>
        <Divider />
        <Box sx={{ mt: 1 }}>
          <SidebarNav collapsed={false} />
        </Box>
      </Drawer>
    );
  }

  const width = sidebarCollapsed ? DRAWER_WIDTH_COLLAPSED : DRAWER_WIDTH;

  return (
    <Drawer
      variant="permanent"
      sx={{
        width,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width,
          boxSizing: 'border-box',
          transition: (theme) =>
            theme.transitions.create('width', {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.enteringScreen,
            }),
          overflowX: 'hidden',
        },
      }}
    >
      <Toolbar>
        <Typography
          variant="h6"
          noWrap
          sx={{ fontWeight: 700, opacity: sidebarCollapsed ? 0 : 1, transition: 'opacity 0.2s' }}
        >
          Research Dashboard
        </Typography>
      </Toolbar>
      <Divider />
      <Box sx={{ mt: 1 }}>
        <SidebarNav collapsed={sidebarCollapsed} />
      </Box>
    </Drawer>
  );
}
