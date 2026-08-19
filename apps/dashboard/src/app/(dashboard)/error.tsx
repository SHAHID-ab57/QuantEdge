'use client';

import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';

export default function DashboardError({
  error,
  reset,
}: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
      <Alert severity="error" sx={{ maxWidth: 560, width: '100%' }}>
        <AlertTitle>Dashboard error</AlertTitle>
        <Box component="pre" sx={{ m: 0, mb: 2, fontSize: 12, overflow: 'auto' }}>
          {error.message}
        </Box>
        <Button variant="contained" color="primary" onClick={reset}>
          Try again
        </Button>
      </Alert>
    </Box>
  );
}
