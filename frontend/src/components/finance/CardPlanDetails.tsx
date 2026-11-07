import { useState, type FormEvent } from "react";
import { type CardPlan, useCardMutation } from "../../api/creditCards";
import { parsePlnToGrosze } from "../../api/finance";
import { formatPLN } from "../../lib/format";
import { loanApiErrorMessage } from "../../api/loans";
import { CardRemoveRecord } from "./CardRemoveRecord";

export function CardPlanDetails({
  accountId,
  plan,
}: {
  accountId: string;
  plan: CardPlan;
}) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState(() =>
    plan.installments.map((item) => ({
      due_date: item.due_date,
      principal_pln: String(item.principal_pln / 100),
      interest_pln: String(item.interest_pln / 100),
      fees_pln: String(item.fees_pln / 100),
    })),
  );
  const [error, setError] = useState<string | null>(null);
  const mutation = useCardMutation(
    accountId,
    `/plans/${plan.id}/schedule`,
    "put",
  );
  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const installments = rows.map((row, index) => ({
      number: index + 1,
      due_date: row.due_date,
      principal_pln: parsePlnToGrosze(row.principal_pln, true),
      interest_pln: parsePlnToGrosze(row.interest_pln, true),
      fees_pln: parsePlnToGrosze(row.fees_pln, true),
    }));
    if (
      installments.some(
        (item) =>
          !item.due_date ||
          item.principal_pln === null ||
          item.interest_pln === null ||
          item.fees_pln === null,
      )
    ) {
      setError("Sprawdź daty i kwoty harmonogramu.");
      return;
    }
    try {
      await mutation.mutateAsync({
        expected_version: plan.version,
        installments,
      });
      setEditing(false);
    } catch (reason) {
      setError(loanApiErrorMessage(reason));
    }
  }
  return (
    <article className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold text-white">{plan.name}</h3>
        <span>{plan.status === "closed" ? "Zamknięty" : "Aktywny"}</span>
      </div>
      <p className="text-sm">
        Oprocentowanie planu: {plan.apr}% · Kapitał:{" "}
        {formatPLN(plan.principal_pln)} PLN · Pozostały kapitał:{" "}
        {formatPLN(plan.remaining_principal_pln)} PLN
      </p>
      <p className="text-sm text-gray-400">
        {plan.schedule_kind === "bank"
          ? "Harmonogram bankowy"
          : "Harmonogram szacunkowy: równy kapitał, APR/12, zaokrąglenie do grosza"}
        . Harmonogram nie księguje odsetek ani opłat.
      </p>
      <details>
        <summary className="cursor-pointer">
          Pokaż harmonogram ({plan.installments.length} rat)
        </summary>
        <div className="overflow-x-auto">
          <table className="mt-3 w-full text-left text-sm">
            <thead>
              <tr>
                {[
                  "Rata",
                  "Termin",
                  "Kapitał PLN",
                  "Odsetki PLN",
                  "Opłaty PLN",
                ].map((label) => (
                  <th className="p-2" key={label}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {plan.installments.map((item) => (
                <tr key={item.number}>
                  {[
                    item.number,
                    item.due_date,
                    formatPLN(item.principal_pln),
                    formatPLN(item.interest_pln),
                    formatPLN(item.fees_pln),
                  ].map((value, index) => (
                    <td className="p-2 tabular-nums" key={index}>
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      {plan.status === "active" ? (
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setEditing(!editing)}
        >
          Uzgodnij harmonogram z bankiem
        </button>
      ) : null}
      {editing ? (
        <form
          onSubmit={save}
          aria-label={`Harmonogram bankowy ${plan.name}`}
          className="space-y-3"
        >
          <p className="text-sm text-gray-400">
            Podaj kwoty z banku. Suma kapitału musi pozostać bez zmian. Po
            przypisaniu spłat harmonogram jest chroniony.
          </p>
          {rows.map((row, index) => (
            <fieldset
              key={index}
              disabled={mutation.isPending}
              className="grid grid-cols-1 gap-2 rounded border border-gray-700 p-3 sm:grid-cols-4"
            >
              <legend>Rata {index + 1}</legend>
              {(
                [
                  "due_date",
                  "principal_pln",
                  "interest_pln",
                  "fees_pln",
                ] as const
              ).map((key) => (
                <label key={key} className="text-sm">
                  {key === "due_date"
                    ? "Termin"
                    : key === "principal_pln"
                      ? "Kapitał PLN"
                      : key === "interest_pln"
                        ? "Odsetki PLN"
                        : "Opłaty PLN"}
                  <input
                    aria-label={`${key} rata ${index + 1}`}
                    type={key === "due_date" ? "date" : "text"}
                    inputMode={key === "due_date" ? undefined : "decimal"}
                    required
                    className="input w-full"
                    value={row[key]}
                    onChange={(event) =>
                      setRows((current) =>
                        current.map((value, i) =>
                          i === index
                            ? { ...value, [key]: event.target.value }
                            : value,
                        ),
                      )
                    }
                  />
                </label>
              ))}
              <button
                type="button"
                disabled={rows.length === 1}
                onClick={() =>
                  setRows((current) => current.filter((_, i) => i !== index))
                }
              >
                Usuń ratę
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            className="btn-secondary"
            disabled={mutation.isPending || rows.length >= 600}
            onClick={() =>
              setRows((current) => [
                ...current,
                {
                  due_date: "",
                  principal_pln: "",
                  interest_pln: "0",
                  fees_pln: "0",
                },
              ])
            }
          >
            Dodaj ratę
          </button>
          {error ? (
            <p role="alert" className="text-red-300">
              {error}
            </p>
          ) : null}
          <button className="btn-primary" disabled={mutation.isPending}>
            Zapisz harmonogram bankowy
          </button>
        </form>
      ) : null}
      {plan.status === "active" ? (
        <CardRemoveRecord
          accountId={accountId}
          path={`/plans/${plan.id}`}
          label="Usuń błędny plan (bez usuwania transakcji)"
        />
      ) : null}
    </article>
  );
}
