import DashboardIcon from '@mui/icons-material/Dashboard';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Overview of markets, positions, and platform health."
      />
      <PlaceholderPage
        icon={<DashboardIcon />}
        title="Dashboard"
        description="Summary widgets for market overview, recent activity, and system status will be wired up here."
      />
    </>
  );
}
