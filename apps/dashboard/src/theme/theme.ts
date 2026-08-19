import { createTheme } from '@mui/material/styles';
import { componentOverrides } from './overrides';

export const theme = createTheme({
  cssVariables: {
    colorSchemeSelector: 'class',
  },
  colorSchemes: {
    dark: {
      palette: {
        background: {
          default: '#0a0e17',
          paper: '#111725',
        },
        primary: {
          main: '#3b82f6',
        },
        success: {
          main: '#22c55e',
        },
        error: {
          main: '#ef4444',
        },
        warning: {
          main: '#f59e0b',
        },
        info: {
          main: '#38bdf8',
        },
        text: {
          primary: '#e5e7eb',
          secondary: '#9ca3af',
        },
        divider: 'rgba(148, 163, 184, 0.16)',
      },
    },
  },
  defaultColorScheme: 'dark',
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: "'Inter', 'Roboto', 'Helvetica Neue', Arial, sans-serif",
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 600,
    },
    button: {
      textTransform: 'none',
      fontWeight: 600,
    },
  },
  components: componentOverrides,
});
