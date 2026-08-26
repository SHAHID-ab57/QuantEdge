import { PageHeader } from '@/components/layout/page-header';
import { ExperimentsPage } from '@/features/experiments/experiments-page';

export default function ExperimentsRoute() {
  return (
    <>
      <PageHeader
        title="Experiments"
        subtitle="Register, search, and track every experiment run over a versioned ML dataset."
      />
      <ExperimentsPage />
    </>
  );
}
