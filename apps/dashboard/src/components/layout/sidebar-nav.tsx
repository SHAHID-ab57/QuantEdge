'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import type { Route } from 'next';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Tooltip from '@mui/material/Tooltip';
import type { SvgIconComponent } from '@mui/icons-material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import CandlestickChartIcon from '@mui/icons-material/CandlestickChart';
import HistoryIcon from '@mui/icons-material/History';
import BoltIcon from '@mui/icons-material/Bolt';
import TableChartIcon from '@mui/icons-material/TableChart';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import ReplayIcon from '@mui/icons-material/Replay';
import FunctionsIcon from '@mui/icons-material/Functions';
import DatasetIcon from '@mui/icons-material/Dataset';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import BiotechIcon from '@mui/icons-material/Biotech';
import LeaderboardIcon from '@mui/icons-material/Leaderboard';
import ModelTrainingIcon from '@mui/icons-material/ModelTraining';
import ScienceIcon from '@mui/icons-material/Science';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SettingsIcon from '@mui/icons-material/Settings';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';

interface NavItem {
  label: string;
  href: Route;
  icon: SvgIconComponent;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: DashboardIcon },
  { label: 'Markets', href: '/markets', icon: CandlestickChartIcon },
  { label: 'History', href: '/history', icon: HistoryIcon },
  { label: 'Live Market', href: '/live-market', icon: BoltIcon },
  { label: 'Order Book', href: '/orderbook', icon: TableChartIcon },
  { label: 'Trade Analytics', href: '/trades', icon: ReceiptLongIcon },
  { label: 'Replay', href: '/replay', icon: ReplayIcon },
  { label: 'Indicators', href: '/indicators', icon: FunctionsIcon },
  { label: 'Features', href: '/features', icon: DatasetIcon },
  { label: 'Validation', href: '/validation', icon: FactCheckIcon },
  { label: 'ML Datasets', href: '/ml-datasets', icon: ModelTrainingIcon },
  { label: 'Experiments', href: '/experiments', icon: BiotechIcon },
  { label: 'Training', href: '/ml/training', icon: SmartToyIcon },
  { label: 'Evaluation', href: '/ml/evaluation', icon: LeaderboardIcon },
  { label: 'Research', href: '/research', icon: ScienceIcon },
  { label: 'Settings', href: '/settings', icon: SettingsIcon },
  { label: 'Health', href: '/health', icon: HealthAndSafetyIcon },
];

export function SidebarNav({ collapsed }: Readonly<{ collapsed: boolean }>) {
  const pathname = usePathname();

  return (
    <List disablePadding>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const selected = pathname === item.href || pathname.startsWith(`${item.href}/`);
        const button = (
          <ListItemButton
            component={Link}
            href={item.href}
            selected={selected}
            sx={{
              minHeight: 44,
              justifyContent: collapsed ? 'center' : 'flex-start',
              px: collapsed ? 1 : 2,
            }}
          >
            <ListItemIcon sx={{ minWidth: 40, justifyContent: 'center' }}>
              <Icon fontSize="small" />
            </ListItemIcon>
            {!collapsed && <ListItemText primary={item.label} />}
          </ListItemButton>
        );
        return (
          <Tooltip
            key={item.href}
            title={item.label}
            placement="right"
            arrow={false}
            disableHoverListener={!collapsed}
          >
            {button}
          </Tooltip>
        );
      })}
    </List>
  );
}
