import { PageHeader } from '@/components/layout/page-header';
import { MLTrainingPage } from '@/features/ml-training/ml-training-page';

export default function MLTrainingRoute() {
  return (
    <>
      <PageHeader
        title="Training"
        subtitle="Register, run, and monitor placeholder training jobs against an experiment."
      />
      <MLTrainingPage />
    </>
  );
}
