import { PageHeader } from '@/components/layout/page-header';
import { ExperimentDetailPage } from '@/features/experiments/experiment-detail-page';

export default async function ExperimentDetailRoute({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <>
      <PageHeader
        title="Experiment Detail"
        subtitle="Metadata, metrics, notes, tags, and artifacts."
      />
      <ExperimentDetailPage experimentId={id} />
    </>
  );
}
