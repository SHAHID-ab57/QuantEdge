'use client';

import { QueryProvider } from './query-provider';
import { ThemeRegistry } from './theme-registry';

export function AppProviders({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <ThemeRegistry>
      <QueryProvider>{children}</QueryProvider>
    </ThemeRegistry>
  );
}
