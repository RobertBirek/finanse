import type { Account } from "../../../api/finance";

export function ImportAccountMapping({
  accounts,
  value,
  onChange,
  label = "Rachunek źródłowy",
  currency,
  exclude,
}: {
  accounts: Account[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
  currency?: string;
  exclude?: string;
}) {
  return (
    <label className="block text-sm">
      {label}
      <select
        className="input mt-1 block w-full"
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Wybierz własny rachunek</option>
        {accounts
          .filter(
            (account) =>
              account.id !== exclude &&
              (!currency || account.currency === currency),
          )
          .map((account) => (
            <option value={account.id} key={account.id}>
              {account.name} · {account.currency}
              {!account.is_active ? " (nieaktywny)" : ""}
            </option>
          ))}
      </select>
    </label>
  );
}
