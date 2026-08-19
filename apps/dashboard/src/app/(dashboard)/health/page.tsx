import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function HealthPage() {
  return (
    <>
      <PageHeader title="Health" subtitle="Service status and infrastructure health." />
      <PlaceholderPage
        icon={<HealthAndSafetyIcon />}
        title="Health"
        description="API, WebSocket, and pipeline service status will be reported here."
      />
    </>
  );
}
