import CandlestickChartIcon from '@mui/icons-material/CandlestickChart';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function MarketsPage() {
  return (
    <>
      <PageHeader title="Markets" subtitle="Browse live markets, symbols, and trading pairs." />
      <PlaceholderPage
        icon={<CandlestickChartIcon />}
        title="Markets"
        description="Market directory and symbol overview will be listed here."
      />
    </>
  );
}
