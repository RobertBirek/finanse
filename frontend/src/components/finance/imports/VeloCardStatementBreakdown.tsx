import { useId } from "react";
import type {
  VeloCardBreakdown,
  VeloCardCharge,
} from "../../../api/bankImports";
import { formatCalendarDate } from "../../../lib/date";
import { sourceMoney } from "./importPresentation";

const unknown = "Brak danych w odczycie";
const chargeLabels = {
  principal: "Kapitał raty",
  plan_interest: "Odsetki planu",
  cash_interest: "Odsetki od transakcji gotówkowych",
} satisfies Record<VeloCardCharge["kind"], string>;

function money(amount: number | null) {
  return amount === null ? unknown : sourceMoney(amount, "PLN");
}

function StatementValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-gray-600 dark:text-gray-400">{label}</dt>
      <dd className="mt-1 font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function StatementCharges({ charges }: { charges: VeloCardCharge[] }) {
  return (
    <ul className="space-y-1">
      {charges.map((charge) => (
        <li
          key={charge.row_key}
          className="flex flex-wrap justify-between gap-x-4"
        >
          <span>
            {charge.kind === "cash_interest"
              ? "Data księgowania"
              : chargeLabels[charge.kind]}{" "}
            <time dateTime={charge.booking_date}>
              {formatCalendarDate(charge.booking_date)}
            </time>
          </span>
          <span className="font-semibold tabular-nums">
            {money(charge.amount_pln)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function VeloCardStatementBreakdown({
  breakdown,
  sourceName,
}: {
  breakdown: VeloCardBreakdown;
  sourceName?: string;
}) {
  const titleId = useId();
  const installment = breakdown.komfort_installment;
  const due = breakdown.due_date;
  return (
    <section className="card space-y-4" aria-labelledby={titleId}>
      <div>
        <h2 id={titleId} className="text-xl">
          Co składa się na spłatę karty
        </h2>
        {sourceName ? (
          <p className="break-words text-sm text-gray-600 dark:text-gray-400">
            {sourceName}
          </p>
        ) : null}
      </div>
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <StatementValue
          label="Minimalna kwota do spłaty"
          value={money(breakdown.minimum_pln)}
        />
        <StatementValue
          label="Termin spłaty"
          value={due ? formatCalendarDate(due) : unknown}
        />
        <StatementValue
          label="Saldo zadłużenia na koniec okresu"
          value={money(breakdown.cycle_debt_pln)}
        />
        <StatementValue
          label="Kapitał przyszłych rat"
          value={money(breakdown.future_installment_principal_pln)}
        />
      </dl>
      <div className="space-y-2 border-t border-gray-200 pt-3 text-sm dark:border-gray-700">
        {installment ? (
          <>
            <h3 className="font-semibold">Rata planu „Komfort”</h3>
            <dl className="grid gap-3 sm:grid-cols-3">
              <StatementValue
                label="Kapitał raty"
                value={money(installment.principal_pln)}
              />
              <StatementValue
                label="Odsetki planu"
                value={money(installment.interest_pln)}
              />
              <StatementValue
                label="Razem rata"
                value={money(installment.total_pln)}
              />
            </dl>
            <p>
              {installment.included_in_minimum
                ? "Rata jest już ujęta w minimalnej kwocie do spłaty."
                : "Brak potwierdzenia, ile z tej raty ujęto w minimalnej kwocie do spłaty."}
            </p>
          </>
        ) : (
          <>
            <h3 className="font-semibold">Pozycje rat na wyciągu</h3>
            {breakdown.unassigned_installment_charges.length ? (
              <>
                <p>Brak jednoznacznego powiązania pozycji z jedną ratą.</p>
                <StatementCharges
                  charges={breakdown.unassigned_installment_charges}
                />
              </>
            ) : (
              <p>{unknown}</p>
            )}
          </>
        )}
      </div>
      <div className="space-y-2 border-t border-gray-200 pt-3 text-sm dark:border-gray-700">
        <h3 className="font-semibold">{chargeLabels.cash_interest}</h3>
        {breakdown.cash_interest_charges.length ? (
          <StatementCharges charges={breakdown.cash_interest_charges} />
        ) : (
          <p>{unknown}</p>
        )}
      </div>
    </section>
  );
}
