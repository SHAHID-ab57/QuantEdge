import ScienceIcon from '@mui/icons-material/Science';
import { PageHeader } from '@/components/layout/page-header';
import { PlaceholderPage } from '@/components/ui/placeholder-page';

export default function ResearchPage() {
  return (
    <>
      <PageHeader title="Research" subtitle="AI-powered analysis and prediction workflows." />
      <PlaceholderPage
        icon={<ScienceIcon />}
        title="Research"
        description="AI models, prediction runs, and research workflows will be managed here."
      />
    </>
  );
}
