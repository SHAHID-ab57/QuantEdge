import { Suspense } from 'react';
import { PageHeader } from '@/components/layout/page-header';
import { LiveMarketPage as LiveMarketPageContent } from '@/features/live-market/live-market-page';

export default function LiveMarketPage() {
  return (
    <>
      <PageHeader title="Live Market" subtitle="Real-time price, chart, and trade tape." />
      {/* The page reads `useSearchParams` for its market/timeframe selection,
          which needs a boundary here so it doesn't deopt the whole route to
          client rendering — same as History and Markets. */}
      <Suspense fallback={null}>
        <LiveMarketPageContent />
      </Suspense>
    </>
  );
}
