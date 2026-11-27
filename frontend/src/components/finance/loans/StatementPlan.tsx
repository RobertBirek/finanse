import { Link } from "react-router-dom";
import type { CardStatementPlanObservation } from "../../../api/loans";
import { formatPLN } from "../../../lib/format";
import { formatCalendarDate } from "../../../lib/date";

export function StatementPlan({
  item,
  title,
}: {
  item: CardStatementPlanObservation;
  title: string;
}) {
  return (
    <article className="rounded-lg border border-gray-700 p-4 space-y-2">
      <h3 className="font-semibold">{title}</h3>
      <p className="text-sm">
        Wyciąg na dzień {formatCalendarDate(item.period_end)}
      </p>
      <p>
        Kwota planu{" "}
        {item.breakdown.installment_original_principal_pln == null
          ? "brak danych"
          : `${formatPLN(item.breakdown.installment_original_principal_pln)} PLN`}{" "}
        · Kapitał przyszłych rat{" "}
        {item.breakdown.future_installment_principal_pln == null
          ? "brak danych"
          : `${formatPLN(item.breakdown.future_installment_principal_pln)} PLN`}
      </p>
      {item.breakdown.komfort_installment ? (
        <>
          <p>
            Rata {formatPLN(item.breakdown.komfort_installment.total_pln)} PLN ·
            kapitał{" "}
            {formatPLN(item.breakdown.komfort_installment.principal_pln)} PLN ·
            odsetki {formatPLN(item.breakdown.komfort_installment.interest_pln)}{" "}
            PLN
          </p>
          {item.breakdown.komfort_installment.included_in_minimum ? (
            <p className="text-sm">
              Rata jest ujęta w kwocie minimalnej wyciągu.
            </p>
          ) : null}
        </>
      ) : (
        <div>
          <p>Brak jednoznacznego powiązania pozycji z jedną ratą.</p>
          <ul>
            {item.breakdown.unassigned_installment_charges.map((charge) => (
              <li key={charge.row_key}>
                {charge.kind === "principal" ? "Kapitał" : "Odsetki"} ·{" "}
                {formatCalendarDate(charge.booking_date)} ·{" "}
                {formatPLN(charge.amount_pln)} PLN
              </li>
            ))}
          </ul>
        </div>
      )}
      <p>
        Minimalna kwota do spłaty{" "}
        {item.breakdown.minimum_pln == null
          ? "brak danych"
          : `${formatPLN(item.breakdown.minimum_pln)} PLN`}{" "}
        · Termin{" "}
        {item.breakdown.due_date
          ? formatCalendarDate(item.breakdown.due_date)
          : "brak danych"}
      </p>
      <Link
        className="underline"
        to={`/finances/imports/${encodeURIComponent(item.batch_id)}`}
      >
        Otwórz wyciąg
      </Link>
    </article>
  );
}
