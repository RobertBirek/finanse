import { useState, type FormEvent } from "react";
import {
  loanAmountToGrosze,
  loanApiErrorMessage,
  useCreateLoanInstallment,
  useUpdateLoanInstallment,
  type LoanInstallment,
  type LoanInstallmentInput,
} from "../../../api/loans";

type Props = {
  loanId: string;
  onSuccess: () => void;
  installment?: LoanInstallment;
  onCancel?: () => void;
};

export function LoanInstallmentForm({
  loanId,
  onSuccess,
  installment,
  onCancel,
}: Props) {
  const create = useCreateLoanInstallment();
  const update = useUpdateLoanInstallment();
  const mutation = installment ? update : create;
  const [number, setNumber] = useState(String(installment?.number ?? ""));
  const [dueDate, setDueDate] = useState(installment?.due_date ?? "");
  const [principal, setPrincipal] = useState(
    ((installment?.principal_pln ?? 0) / 100).toFixed(2),
  );
  const [interest, setInterest] = useState(
    ((installment?.interest_pln ?? 0) / 100).toFixed(2),
  );
  const [fees, setFees] = useState(
    ((installment?.fees_pln ?? 0) / 100).toFixed(2),
  );
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const values = [
    loanAmountToGrosze(principal),
    loanAmountToGrosze(interest),
    loanAmountToGrosze(fees),
  ];
  const total = values.every((value) => value !== null)
    ? (values[0] ?? 0) + (values[1] ?? 0) + (values[2] ?? 0)
    : null;
  const valid =
    Number.isSafeInteger(Number(number)) &&
    Number(number) > 0 &&
    !!dueDate &&
    total !== null &&
    Number.isSafeInteger(total) &&
    total > 0;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid || total === null) return;
    const payload: LoanInstallmentInput = {
      number: Number(number),
      due_date: dueDate,
      principal_pln: values[0] ?? 0,
      interest_pln: values[1] ?? 0,
      fees_pln: values[2] ?? 0,
    };
    setSubmissionError(null);
    const success = () => {
      if (!installment) {
        setNumber("");
        setDueDate("");
        setPrincipal("0.00");
        setInterest("0.00");
        setFees("0.00");
      }
      onSuccess();
    };
    const failure = (error: unknown) =>
      setSubmissionError(loanApiErrorMessage(error));
    if (installment)
      update.mutate(
        { loanId, installmentId: installment.id, ...payload },
        { onSuccess: success, onError: failure },
      );
    else
      create.mutate(
        { loanId, ...payload },
        { onSuccess: success, onError: failure },
      );
  }
  const fields: Array<[string, string, (value: string) => void]> = [
    ["Kapitał", principal, setPrincipal],
    ["Odsetki", interest, setInterest],
    ["Opłaty", fees, setFees],
  ];
  return (
    <form
      aria-label={installment ? "Edytuj ratę" : "Nowa rata"}
      onSubmit={submit}
      className="card mb-4"
    >
      <h3 className="mb-3 text-base font-semibold text-white">
        {installment ? "Edytuj ratę" : "Nowa rata"}
      </h3>
      <p className="mb-3 text-xs text-gray-500">
        Składniki planu mogą wynosić 0, ale suma raty musi być większa od 0.
      </p>
      <div className="grid gap-3 sm:grid-cols-5">
        <label className="text-sm text-gray-400">
          Numer
          <input
            className="input mt-1"
            type="number"
            min="1"
            value={number}
            onChange={(event) => setNumber(event.target.value)}
          />
        </label>
        <label className="text-sm text-gray-400">
          Termin
          <input
            className="input mt-1"
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
          />
        </label>
        {fields.map(([label, value, setter]) => (
          <label key={label} className="text-sm text-gray-400">
            {label} (PLN)
            <input
              className="input mt-1"
              value={value}
              onChange={(event) => setter(event.target.value)}
            />
          </label>
        ))}
      </div>
      {total !== null ? (
        <p className="mt-3 text-sm text-gray-400">
          Suma planu: {(total / 100).toFixed(2)} PLN
        </p>
      ) : (
        <p className="mt-3 text-sm text-red-400">Podaj poprawne kwoty.</p>
      )}
      {(submissionError ?? loanApiErrorMessage(mutation.error)) ? (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {submissionError ?? loanApiErrorMessage(mutation.error)}
        </p>
      ) : null}
      <div className="mt-4 flex gap-2">
        <button className="btn-primary" disabled={!valid || mutation.isPending}>
          {installment ? "Zapisz ratę" : "Dodaj ratę"}
        </button>
        {onCancel ? (
          <button className="btn-secondary" type="button" onClick={onCancel}>
            Anuluj
          </button>
        ) : null}
      </div>
    </form>
  );
}
