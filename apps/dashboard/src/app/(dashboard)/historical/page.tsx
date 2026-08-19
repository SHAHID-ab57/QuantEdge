import HistoryIcon from '@mui/icons-material/History';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function HistoricalDataPage() {
  return (
    <>
      <PageHeader
        title="Historical Data"
        subtitle="Query candle history and market data quality."
      />
      <PlaceholderPage
        icon={<HistoryIcon />}
        title="Historical Data"
        description="Historical candle and trade data queries will be available here."
      />
    </>
  );
}
