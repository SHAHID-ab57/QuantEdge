import { PageHeader } from '@/components/layout/page-header';
import { NewsPage } from '@/features/news/news-page';

export default function NewsRoute() {
  return (
    <>
      <PageHeader
        title="News"
        subtitle="Real, tracked-symbol news articles and their own sentiment — what the News data source on /data-sources is summarizing."
      />
      <NewsPage />
    </>
  );
}
