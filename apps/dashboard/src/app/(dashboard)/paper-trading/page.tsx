import { PageHeader } from '@/components/layout/page-header';
import { PaperTradingPage } from '@/features/paper-trading/paper-trading-page';

export default function PaperTradingRoute() {
  return (
    <>
      <PageHeader
        title="Paper Trading"
        subtitle="Place simulated market orders against real prices — realistic slippage and fees, always applied."
      />
      <PaperTradingPage />
    </>
  );
}
