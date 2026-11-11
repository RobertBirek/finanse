import { Link } from "react-router-dom";
import type { ScheduleResult } from "../../../api/loanScheduleImports";

export function ScheduleReceipt({ result }: { result: ScheduleResult }) {
  return (
    <section className="card space-y-3" aria-label="Potwierdzenie aktywacji">
      <h2 className="text-xl">Harmonogram aktywowany</h2>
      <p>Księga pozostaje bez zmian. Zachowano zgodne raty i powiązania.</p>
      <p className="break-all text-sm">
        Potwierdzenie: {result.receipt_id} · wersja: {result.revision_id}
      </p>
      <p>
        Zgodne raty: {result.reused_ids.length} · nowe: {result.new_ids.length}{" "}
        · wycofane przyszłe: {result.superseded_ids.length}
      </p>
      <Link
        className="underline"
        to={`/settings/finances/loans?loan=${encodeURIComponent(result.loan_id)}`}
      >
        Otwórz kredyt i historię wersji
      </Link>
    </section>
  );
}
