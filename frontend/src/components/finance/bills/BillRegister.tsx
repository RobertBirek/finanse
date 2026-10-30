import { Link } from "react-router-dom";
import type { BillResponse } from "../../../api/bills";

const amount = (value: number, currency: string) =>
  new Intl.NumberFormat("pl-PL", { style: "currency", currency }).format(
    value / 100,
  );
const date = (value: string | null) =>
  value
    ? new Date(`${value}T00:00:00`).toLocaleDateString("pl-PL")
    : "Brak terminu";

export function BillRegister({
  bills,
  onSelect,
}: {
  bills: BillResponse[];
  onSelect: (id: string) => void;
}) {
  if (!bills.length)
    return (
      <p className="card text-sm text-gray-500">
        Brak dokumentów dla wybranych filtrów.
      </p>
    );
  return (
    <div className="space-y-2">
      {bills.map((bill) => {
        const overdue =
          bill.due_date &&
          bill.remaining_minor > 0 &&
          bill.due_date < new Date().toISOString().slice(0, 10);
        return (
          <article
            key={bill.id}
            className="card flex flex-wrap items-center justify-between gap-3 p-4"
          >
            <div>
              <button
                type="button"
                onClick={() => onSelect(bill.id)}
                className="text-left font-medium text-white hover:text-advisor-300"
              >
                {bill.supplier_name ?? "Dokument bez sprzedawcy"}
                {bill.number ? ` · ${bill.number}` : ""}
              </button>
              <p
                className={`mt-1 text-xs ${overdue ? "text-red-300" : "text-gray-400"}`}
              >
                {date(bill.issue_date)} · {overdue ? "Zaległe: " : "Termin: "}
                {date(bill.due_date)} ·{" "}
                {bill.declaration === "declared_paid"
                  ? "Deklarowano opłacenie"
                  : "Bez deklaracji opłacenia"}{" "}
                · Uzgodnienie: {bill.reconciliation}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-5 text-right text-xs">
              <div>
                <dt className="text-gray-500">Suma</dt>
                <dd className="font-mono text-white">
                  {bill.total_minor == null || !bill.currency
                    ? "—"
                    : amount(bill.total_minor, bill.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-500">Pozostało</dt>
                <dd className="font-mono text-white">
                  {bill.total_minor == null || !bill.currency
                    ? "—"
                    : amount(bill.remaining_minor, bill.currency)}
                </dd>
              </div>
            </dl>
            <Link
              to={`/finances/documents?bill=${bill.id}`}
              className="text-sm text-advisor-400 hover:underline"
            >
              Szczegóły
            </Link>
          </article>
        );
      })}
    </div>
  );
}
