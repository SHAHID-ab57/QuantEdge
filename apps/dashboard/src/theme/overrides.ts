import type { ThemeOptions } from '@mui/material/styles';

export const componentOverrides: ThemeOptions['components'] = {
  MuiCssBaseline: {
    styleOverrides: {
      body: {
        fontFeatureSettings: "'tnum'",
      },
    },
  },
  MuiPaper: {
    defaultProps: {
      variant: 'outlined',
    },
  },
  MuiListItemButton: {
    styleOverrides: {
      root: {
        borderRadius: 8,
        margin: '0 8px',
        '&.Mui-selected': {
          backgroundColor: 'action.selected',
        },
      },
    },
  },
  MuiDrawer: {
    styleOverrides: {
      paper: {
        borderRight: '1px solid',
        borderColor: 'divider',
      },
    },
  },
};
