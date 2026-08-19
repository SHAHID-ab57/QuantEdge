import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';

export default function Loading() {
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <Skeleton variant="text" width={240} height={40} />
      <Skeleton variant="text" width={360} height={20} />
      <Skeleton variant="rounded" height={320} />
    </Stack>
  );
}
