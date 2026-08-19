import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';

export function LoadingScreen() {
  return (
    <Box sx={{ width: '100%', mt: 2 }}>
      <LinearProgress color="primary" />
    </Box>
  );
}
