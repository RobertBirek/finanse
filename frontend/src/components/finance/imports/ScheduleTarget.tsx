import type { Account } from "../../../api/finance";
import type { Loan } from "../../../api/loans";
import type { ScheduleTargetData } from "../../../api/loanScheduleImports";

export function ScheduleTarget({
  value,
  onChange,
  loans,
  accounts,
  disabled = false,
}: {
  value: ScheduleTargetData;
  onChange: (value: ScheduleTargetData) => void;
  loans: Loan[];
  accounts: Account[];
  disabled?: boolean;
}) {
  const fresh = value.new_loan;
  const eligible = accounts.filter(
    (a) =>
      a.is_active &&
      a.currency === "PLN" &&
      a.type !== "credit_card" &&
      !a.credit_card,
  );
  return (
    <fieldset disabled={disabled} className="card space-y-4">
      <legend className="text-xl">Przypisanie do kredytu</legend>
      <div className="flex flex-wrap gap-4">
        <label>
          <input
            type="radio"
            name="schedule-target"
            checked={!fresh}
            onChange={() => onChange({ loan_id: null, new_loan: null })}
          />{" "}
          Istniejący kredyt
        </label>
        <label>
          <input
            type="radio"
            name="schedule-target"
            checked={!!fresh}
            onChange={() =>
              onChange({
                loan_id: null,
                new_loan: { name: "", account_id: "", payment_account_id: "" },
              })
            }
          />{" "}
          Nowy kredyt
        </label>
      </div>
      {fresh ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="sm:col-span-2">
            Nazwa nowej umowy
            <input
              className="input mt-1 w-full"
              value={fresh.name}
              onChange={(e) =>
                onChange({
                  ...value,
                  new_loan: { ...fresh, name: e.target.value },
                })
              }
            />
          </label>
          {(
            [
              ["account_id", "Konto długu"],
              ["payment_account_id", "Konto spłaty"],
            ] as const
          ).map(([field, label]) => (
            <label key={field}>
              {label}
              <select
                className="input mt-1 w-full"
                value={fresh[field]}
                onChange={(e) =>
                  onChange({
                    ...value,
                    new_loan: { ...fresh, [field]: e.target.value },
                  })
                }
              >
                <option value="">Wybierz konto PLN</option>
                {eligible.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <p className="text-sm sm:col-span-2">
            Nowa umowa powstanie dopiero po jawnej aktywacji. Konta muszą być
            różne.
          </p>
        </div>
      ) : (
        <label className="block">
          Kredyt
          <select
            className="input mt-1 w-full"
            value={value.loan_id ?? ""}
            onChange={(e) =>
              onChange({ loan_id: e.target.value || null, new_loan: null })
            }
          >
            <option value="">Wybierz istniejącą umowę</option>
            {loans
              .filter((l) => l.is_active)
              .map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
          </select>
        </label>
      )}
    </fieldset>
  );
}
