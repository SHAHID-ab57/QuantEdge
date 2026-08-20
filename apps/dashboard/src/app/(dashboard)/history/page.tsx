import { PageHeader } from '@/components/layout/page-header';
import { HistoryPage } from '@/features/history/history-page';

export default function HistoryRoute() {
  return (
    <>
      <PageHeader
        title="History"
        subtitle="Explore historical OHLCV candles, statistics, and exports."
      />
      <HistoryPage />
    </>
  );
}
