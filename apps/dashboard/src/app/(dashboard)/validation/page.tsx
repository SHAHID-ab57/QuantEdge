import { PageHeader } from '@/components/layout/page-header';
import { DatasetValidationPage } from '@/features/dataset-validation/dataset-validation-page';

export default function ValidationPage() {
  return (
    <>
      <PageHeader
        title="Dataset Validation"
        subtitle="Run the validation engine's structural, data-quality, time-series, and feature checks against a built dataset."
      />
      <DatasetValidationPage />
    </>
  );
}
