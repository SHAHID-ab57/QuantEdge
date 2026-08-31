'use client';

import { lazy, Suspense, useEffect, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createQueryClient } from '@/lib/query/queryClient';

const ReactQueryDevtools =
  process.env.NODE_ENV === 'development'
    ? lazy(() =>
        import('@tanstack/react-query-devtools').then((module) => ({
          default: module.ReactQueryDevtools,
        })),
      )
    : null;

export function QueryProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(createQueryClient);
  // The devtools panel's own root element carries client-only attributes
  // (e.g. `aria-hidden`, set from its internal open/closed state) that never
  // match whatever Next.js server-rendered — mounting it only after this
  // effect runs guarantees the very first client render is identical to the
  // server's (nothing here yet), so the devtools appear in a later, separate
  // commit instead of during hydration itself.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {mounted && ReactQueryDevtools !== null && (
        <Suspense fallback={null}>
          <ReactQueryDevtools initialIsOpen={false} />
        </Suspense>
      )}
    </QueryClientProvider>
  );
}
