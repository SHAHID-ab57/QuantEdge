'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getSessionToken } from '@/lib/api/session';

/**
 * `sessionStorage` isn't server-readable, so this decision (signed in ->
 * `/dashboard`, signed out -> `/login`) has to happen client-side rather
 * than via a server-side `redirect()` — this route previously always
 * redirected to `/dashboard` unconditionally, before authentication
 * existed.
 */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getSessionToken() ? '/dashboard' : '/login');
  }, [router]);

  return null;
}
