import { Suspense } from 'react';
import { PageHeader } from '@/components/layout/page-header';
import { MarketsPage } from '@/features/markets/markets-page';

export default function MarketsRoute() {
  return (
    <>
      <PageHeader
        title="Markets"
        subtitle="Browse synchronized markets, symbols, and data quality."
      />
      <Suspense fallback={null}>
        <MarketsPage />
      </Suspense>
    </>
  );
}
