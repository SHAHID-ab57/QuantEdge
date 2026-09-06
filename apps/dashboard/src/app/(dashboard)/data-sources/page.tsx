import { PageHeader } from '@/components/layout/page-header';
import { DataSourcesPage } from '@/features/data-sources/data-sources-page';

export default function DataSourcesRoute() {
  return (
    <>
      <PageHeader
        title="Data Sources"
        subtitle="Current values and history from every ingested external data source, and what's planned next."
      />
      <DataSourcesPage />
    </>
  );
}
