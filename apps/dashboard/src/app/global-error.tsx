'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { theme } from '@/theme/theme';

export default function GlobalError({
  error,
  reset,
}: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return (
    <html lang="en">
      <body>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6, px: 2 }}>
            <Alert severity="error" sx={{ maxWidth: 560, width: '100%' }}>
              <AlertTitle>Fatal error</AlertTitle>
              <Box component="pre" sx={{ m: 0, mb: 2, fontSize: 12, overflow: 'auto' }}>
                {error.message}
              </Box>
              <Button variant="contained" color="primary" onClick={reset}>
                Reload
              </Button>
            </Alert>
          </Box>
        </ThemeProvider>
      </body>
    </html>
  );
}
