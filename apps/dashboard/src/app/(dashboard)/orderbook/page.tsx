import { Suspense } from 'react';
import { PageHeader } from '@/components/layout/page-header';
import { OrderBookPage as OrderBookPageContent } from '@/features/order-book/order-book-page';

export default function OrderBookPage() {
  return (
    <>
      <PageHeader title="Order Book" subtitle="Live depth, spread, and mid price." />
      {/* Reads `useSearchParams` for its market selection, so it needs a
          boundary here — same reason History/Markets/Live Market have one. */}
      <Suspense fallback={null}>
        <OrderBookPageContent />
      </Suspense>
    </>
  );
}
