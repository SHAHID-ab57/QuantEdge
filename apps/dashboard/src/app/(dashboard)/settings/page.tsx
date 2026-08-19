import SettingsIcon from '@mui/icons-material/Settings';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" subtitle="Platform and account preferences." />
      <PlaceholderPage
        icon={<SettingsIcon />}
        title="Settings"
        description="Account, connection, and platform preferences will be configured here."
      />
    </>
  );
}
