import { PageHeader } from '@/components/layout/page-header';
import { ReplayPage as ReplayPageContent } from '@/features/replay/replay-page';

export default function ReplayPage() {
  return (
    <>
      <PageHeader
        title="Market Replay"
        subtitle="Step or auto-play through historical candles at a chosen speed."
      />
      <ReplayPageContent />
    </>
  );
}
