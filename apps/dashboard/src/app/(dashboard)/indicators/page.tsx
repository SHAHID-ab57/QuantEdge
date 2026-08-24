import { PageHeader } from '@/components/layout/page-header';
import { IndicatorsPage as IndicatorsPageContent } from '@/features/indicators/indicators-page';

export default function IndicatorsPage() {
  return (
    <>
      <PageHeader
        title="Technical Indicators"
        subtitle="Calculate indicators over stored candles for research and validation."
      />
      <IndicatorsPageContent />
    </>
  );
}
