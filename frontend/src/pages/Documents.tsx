import { DocumentUpload } from "../components/DocumentUpload";
import { DocumentList } from "../components/DocumentList";

export function Documents() {
  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">Dokumenty</h1>
      <DocumentUpload />
      <DocumentList />
    </div>
  );
}
