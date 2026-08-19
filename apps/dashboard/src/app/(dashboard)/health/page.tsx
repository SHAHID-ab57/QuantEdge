import { PageHeader } from '@/components/layout/page-header';
import { HealthPage } from '@/features/health/health-page';

export default function HealthPageRoute() {
  return (
    <>
      <PageHeader
        title="Health"
        subtitle="Service status and infrastructure health. Auto-refreshes every 10 seconds."
      />
      <HealthPage />
    </>
  );
}
