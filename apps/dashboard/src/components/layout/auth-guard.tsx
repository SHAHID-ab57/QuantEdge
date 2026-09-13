'use client';

import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getSessionToken } from '@/lib/api/session';

/**
 * Every dashboard route now sits behind a real login — this is the
 * frontend half of that boundary. Checked client-side (`sessionStorage`
 * isn't server-readable) on mount and redirects to `/login` when no
 * token is present, rather than rendering a page that would immediately
 * fail every request it makes with a generic-looking error.
 *
 * Deliberately just a presence check, not a validity check — an expired
 * or otherwise-rejected token is still caught (by the API client's own
 * 401 interceptor, `src/lib/api/client.ts`, which clears the token and
 * redirects the same way) the first time any page actually calls the
 * API. Duplicating that check here would just be a second source of
 * truth for the same decision.
 */
export function AuthGuard({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!getSessionToken()) {
      router.replace('/login');
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) {
    return (
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100dvh',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  return <>{children}</>;
}
