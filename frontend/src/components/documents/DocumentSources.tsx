import { Link } from "react-router-dom";

export function DocumentSources({ documentIds }: { documentIds: string[] }) {
  if (!documentIds.length) return null;
  return (
    <section
      aria-label="Źródła dokumentu"
      className="mt-4 border-t border-gray-800 pt-4"
    >
      <h3 className="text-sm font-medium text-gray-200">Źródła</h3>
      <p className="mt-1 text-sm text-gray-400">
        Powiązane pliki potwierdzają ten sam zakup; nie tworzą nowej płatności.
      </p>
      <Link
        to="/finances/documents"
        className="mt-2 inline-block text-sm text-advisor-400 hover:underline"
      >
        Otwórz rejestr faktur i paragonów
      </Link>
    </section>
  );
}
