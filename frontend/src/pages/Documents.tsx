import { DocumentUpload } from "../components/DocumentUpload";
import { DocumentList } from "../components/DocumentList";
import { PageHeader } from "../components/PageHeader";

export function Documents() {
  return (
    <div className="page-workspace">
      <PageHeader title="Dokumenty" />
      <DocumentUpload />
      <DocumentList />
    </div>
  );
}
