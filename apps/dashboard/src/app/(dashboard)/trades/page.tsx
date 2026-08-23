import { Suspense } from 'react';
import { PageHeader } from '@/components/layout/page-header';
import { TradesPage as TradesPageContent } from '@/features/trades/trades-page';

export default function TradesPage() {
  return (
    <>
      <PageHeader
        title="Trade Analytics"
        subtitle="Live trade tape, VWAP, and rolling statistics."
      />
      {/* Reads `useSearchParams` for its market selection, so it needs a
          boundary here — same reason History/Markets/Live Market/Order Book have one. */}
      <Suspense fallback={null}>
        <TradesPageContent />
      </Suspense>
    </>
  );
}
