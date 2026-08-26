import { PageHeader } from '@/components/layout/page-header';
import { MLDatasetsPage } from '@/features/ml-datasets/ml-datasets-page';

export default function MLDatasetsRoute() {
  return (
    <>
      <PageHeader
        title="ML Dataset Builder"
        subtitle="Build versioned, leakage-safe, chronologically split datasets for AI training."
      />
      <MLDatasetsPage />
    </>
  );
}
