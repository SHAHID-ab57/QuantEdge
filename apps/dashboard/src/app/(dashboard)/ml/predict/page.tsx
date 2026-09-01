import { PageHeader } from '@/components/layout/page-header';
import { MLPredictPage } from '@/features/ml-predict/ml-predict-page';

export default function MLPredictRoute() {
  return (
    <>
      <PageHeader
        title="Predict"
        subtitle="Run a fresh, live prediction for one market from a completed training job."
      />
      <MLPredictPage />
    </>
  );
}
