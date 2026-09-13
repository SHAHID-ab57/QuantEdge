'use client';

import LogoutIcon from '@mui/icons-material/Logout';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import { useCurrentUser, logout } from '@/features/auth/hooks/use-auth';

/**
 * The one piece of session UI every dashboard page shares: who's signed
 * in, and a way to sign out. Renders nothing while the profile request is
 * still in flight or has no data yet (e.g. the instant after `AuthGuard`
 * has confirmed a token exists but before `GET /auth/me` resolves).
 */
export function UserMenu() {
  const { data: user } = useCurrentUser();

  if (!user) {
    return null;
  }

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Typography
        variant="body2"
        color="text.secondary"
        noWrap
        sx={{ display: { xs: 'none', sm: 'block' } }}
      >
        {user.email}
      </Typography>
      <Tooltip title="Sign out">
        <IconButton color="inherit" aria-label="Sign out" onClick={logout} size="small">
          <LogoutIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
