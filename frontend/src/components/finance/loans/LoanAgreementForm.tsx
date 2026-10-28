import { useState, type FormEvent } from "react";
import {
  eligibleLoanAccounts,
  loanApiErrorMessage,
  useCreateLoan,
  type LoanInput,
} from "../../../api/loans";
import type { Account } from "../../../api/finance";

export function LoanAgreementForm({
  accounts,
  onSuccess,
}: {
  accounts: Account[];
  onSuccess: (id: string) => void;
}) {
  const mutation = useCreateLoan();
  const [name, setName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [paymentAccountId, setPaymentAccountId] = useState("");
  const eligible = eligibleLoanAccounts(accounts);
  const canSubmit =
    name.trim() !== "" &&
    accountId !== "" &&
    paymentAccountId !== "" &&
    accountId !== paymentAccountId;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    const payload: LoanInput = {
      name: name.trim(),
      account_id: accountId,
      payment_account_id: paymentAccountId,
    };
    mutation.mutate(payload, {
      onSuccess: (loan) => {
        setName("");
        setAccountId("");
        setPaymentAccountId("");
        onSuccess(loan.id);
      },
    });
  }
  return (
    <form aria-label="Nowa umowa" onSubmit={submit} className="card mb-5">
      <h2 className="mb-3 text-lg font-semibold text-white">Nowa umowa</h2>
      <p className="mb-4 text-sm text-gray-400">
        Wybierz dwa różne, własne aktywne konta PLN. Konto budżetowe zachowuje
        obecne ustawienie — nie zmieniamy go automatycznie.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm text-gray-400">
          Nazwa
          <input
            className="input mt-1"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="text-sm text-gray-400">
          Konto zadłużenia
          <select
            className="input mt-1"
            value={accountId}
            onChange={(event) => setAccountId(event.target.value)}
          >
            <option value="">Wybierz konto</option>
            {eligible.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-gray-400">
          Rachunek spłaty
          <select
            className="input mt-1"
            value={paymentAccountId}
            onChange={(event) => setPaymentAccountId(event.target.value)}
          >
            <option value="">Wybierz konto</option>
            {eligible.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {loanApiErrorMessage(mutation.error) ? (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {loanApiErrorMessage(mutation.error)}
        </p>
      ) : null}
      <button
        className="btn-primary mt-4"
        disabled={!canSubmit || mutation.isPending}
      >
        Dodaj umowę
      </button>
    </form>
  );
}
