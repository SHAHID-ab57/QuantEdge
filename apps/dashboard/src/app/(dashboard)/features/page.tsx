import { PageHeader } from '@/components/layout/page-header';
import { FeatureEngineeringPage } from '@/features/feature-engineering/feature-engineering-page';

export default function FeaturesPage() {
  return (
    <>
      <PageHeader
        title="Feature Engineering"
        subtitle="Generate versioned, model-ready feature datasets from stored market data."
      />
      <FeatureEngineeringPage />
    </>
  );
}
