import { DocumentUpload } from "../components/DocumentUpload";
import { DocumentList } from "../components/DocumentList";

export function Documents() {
  return (
    <div className="max-w-6xl mx-auto min-w-0">
      <h1 className="text-2xl font-bold text-white mb-4">Dokumenty</h1>
      <DocumentUpload />
      <DocumentList />
    </div>
  );
}
