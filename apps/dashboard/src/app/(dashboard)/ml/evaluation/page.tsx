import { PageHeader } from '@/components/layout/page-header';
import { MLEvaluationPage } from '@/features/ml-evaluation/ml-evaluation-page';

export default function MLEvaluationRoute() {
  return (
    <>
      <PageHeader
        title="Evaluation"
        subtitle="Compare completed training jobs by their recorded metrics and see which model wins."
      />
      <MLEvaluationPage />
    </>
  );
}
