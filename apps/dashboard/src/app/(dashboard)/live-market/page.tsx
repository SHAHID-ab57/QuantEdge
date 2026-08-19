import BoltIcon from '@mui/icons-material/Bolt';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function LiveMarketPage() {
  return (
    <>
      <PageHeader title="Live Market" subtitle="Real-time trades, tickers, and order books." />
      <PlaceholderPage
        icon={<BoltIcon />}
        title="Live Market"
        description="Live WebSocket streams for trades, tickers, and order books will be shown here."
      />
    </>
  );
}
