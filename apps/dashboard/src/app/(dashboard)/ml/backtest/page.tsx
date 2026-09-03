import { PageHeader } from '@/components/layout/page-header';
import { MLBacktestPage } from '@/features/ml-backtest/ml-backtest-page';

export default function MLBacktestRoute() {
  return (
    <>
      <PageHeader
        title="Backtest"
        subtitle="Walk a trained model over a historical date range and report aggregate performance."
      />
      <MLBacktestPage />
    </>
  );
}
