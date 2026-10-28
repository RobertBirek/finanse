import { useState } from "react";
import { useAccounts } from "../api/finance";
import {
  loanApiErrorMessage,
  useDeleteLoanInstallment,
  useLinkLoanPayment,
  useLoan,
  useLoanPaymentCandidates,
  useLoans,
  useUnlinkLoanPayment,
  useUpdateLoan,
  type LoanInstallment,
  type LoanPaymentStatus,
} from "../api/loans";
import { QueryFeedback } from "../components/QueryFeedback";
import { LoanAgreementForm } from "../components/finance/loans/LoanAgreementForm";
import { LoanInstallmentForm } from "../components/finance/loans/LoanInstallmentForm";
import { formatPLN } from "../lib/format";

const statusLabels: Record<LoanPaymentStatus, string> = {
  unpaid: "Niepokryta",
  partial: "Częściowo pokryta",
  paid: "Pokryta",
};

function InstallmentRow({
  loanId,
  installment,
}: {
  loanId: string;
  installment: LoanInstallment;
}) {
  const [showPayments, setShowPayments] = useState(false);
  const [editing, setEditing] = useState(false);
  const [transactionId, setTransactionId] = useState("");
  const [offset, setOffset] = useState(0);
  const deleteMutation = useDeleteLoanInstallment();
  const linkMutation = useLinkLoanPayment();
  const unlinkMutation = useUnlinkLoanPayment();
  const candidates = useLoanPaymentCandidates(
    loanId,
    showPayments ? installment.id : null,
    offset,
  );
  function link(id: string) {
    if (id.trim())
      linkMutation.mutate(
        {
          loanId,
          installmentId: installment.id,
          transactionId: id.trim(),
        },
        {
          onSuccess: () => {
            setOffset(0);
            setTransactionId("");
          },
        },
      );
  }
  return (
    <article className="border-b border-gray-800 py-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-white">
            Rata {installment.number}{" "}
            <span className="ml-2 text-sm font-normal text-gray-300">
              {statusLabels[installment.payment_status]}
            </span>
          </h3>
          <p className="mt-1 text-sm text-gray-400">
            Termin: {installment.due_date} · plan: kapitał{" "}
            {formatPLN(installment.principal_pln)}, odsetki{" "}
            {formatPLN(installment.interest_pln)}, opłaty{" "}
            {formatPLN(installment.fees_pln)} PLN
          </p>
        </div>
        <dl className="flex gap-4 text-sm">
          <div>
            <dt className="text-gray-500">Plan</dt>
            <dd className="font-mono text-white">
              {formatPLN(installment.total_pln)} PLN
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Powiązano</dt>
            <dd className="font-mono text-white">
              {formatPLN(installment.paid_pln)} PLN
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">Do pokrycia</dt>
            <dd className="font-mono text-white">
              {formatPLN(installment.remaining_pln)} PLN
            </dd>
          </div>
        </dl>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {installment.payments.length === 0 ? (
          <button
            className="btn-secondary"
            type="button"
            onClick={() => setEditing(true)}
          >
            Edytuj ratę
          </button>
        ) : null}
        <button
          className="btn-secondary"
          type="button"
          onClick={() => setShowPayments((visible) => !visible)}
        >
          {showPayments ? "Ukryj płatności" : "Powiąż płatność"}
        </button>
        {installment.payments.length === 0 ? (
          <button
            className="btn-secondary"
            type="button"
            disabled={deleteMutation.isPending}
            onClick={() => {
              if (window.confirm("Usunąć niepowiązaną ratę?"))
                deleteMutation.mutate({
                  loanId,
                  installmentId: installment.id,
                });
            }}
          >
            Usuń ratę
          </button>
        ) : null}
      </div>
      {loanApiErrorMessage(deleteMutation.error) ? (
        <p role="alert" className="mt-2 text-sm text-red-400">
          {loanApiErrorMessage(deleteMutation.error)}
        </p>
      ) : null}
      {editing ? (
        <LoanInstallmentForm
          loanId={loanId}
          installment={installment}
          onSuccess={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      ) : null}
      {showPayments ? (
        <section
          className="mt-4 rounded-lg bg-gray-900 p-3"
          aria-label={`Płatności raty ${installment.number}`}
        >
          <p className="mb-2 text-sm text-gray-400">
            Powiązanie jest wyłącznie metadanymi: nie tworzy przelewu ani nie
            księguje historycznych odsetek.
          </p>
          <div className="flex flex-wrap gap-2">
            <label
              className="sr-only"
              htmlFor={`transaction-${installment.id}`}
            >
              ID istniejącego przelewu
            </label>
            <input
              id={`transaction-${installment.id}`}
              className="input"
              value={transactionId}
              placeholder="ID istniejącego przelewu"
              onChange={(event) => setTransactionId(event.target.value)}
            />
            <button
              className="btn-primary"
              type="button"
              disabled={!transactionId.trim() || linkMutation.isPending}
              onClick={() => link(transactionId)}
            >
              Powiąż ID
            </button>
          </div>
          {loanApiErrorMessage(linkMutation.error) ? (
            <p role="alert" className="mt-2 text-sm text-red-400">
              {loanApiErrorMessage(linkMutation.error)}
            </p>
          ) : null}
          <QueryFeedback
            loading={candidates.isLoading}
            error={candidates.isError}
            errorMessage="Nie udało się pobrać kandydatów."
            onRetry={candidates.refetch}
          >
            <div className="mt-4">
              <h4 className="text-sm font-medium text-white">
                Kandydaci do ręcznego wyboru
              </h4>
              {(candidates.data?.items.length ?? 0) === 0 ? (
                <p className="mt-2 text-sm text-gray-500">
                  Brak kwalifikujących się, niepowiązanych transferów. To nie
                  oznacza braku płatności.
                </p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {candidates.data?.items.map((candidate) => (
                    <li
                      key={candidate.transaction_id}
                      className="flex flex-wrap items-center justify-between gap-2 text-sm"
                    >
                      <span>
                        {candidate.transaction_date} ·{" "}
                        {candidate.description || "Bez opisu"} ·{" "}
                        <strong>{formatPLN(candidate.amount_pln)} PLN</strong>
                      </span>
                      <button
                        className="btn-secondary"
                        type="button"
                        disabled={linkMutation.isPending}
                        onClick={() => link(candidate.transaction_id)}
                      >
                        Wybierz
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  className="btn-secondary"
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset((value) => Math.max(0, value - 20))}
                >
                  Poprzednie
                </button>
                <button
                  className="btn-secondary"
                  type="button"
                  disabled={
                    (candidates.data?.offset ?? 0) +
                      (candidates.data?.limit ?? 20) >=
                    (candidates.data?.total ?? 0)
                  }
                  onClick={() => setOffset((value) => value + 20)}
                >
                  Następne
                </button>
              </div>
            </div>
          </QueryFeedback>
          {installment.payments.length > 0 ? (
            <ul className="mt-4 space-y-2 text-sm">
              {installment.payments.map((payment) => (
                <li
                  key={payment.id}
                  className="flex flex-wrap items-center justify-between gap-2"
                >
                  <span>
                    {payment.transaction_date} · {formatPLN(payment.amount_pln)}{" "}
                    PLN · Płatność powiązana; podział księgowy do uzgodnienia.
                  </span>
                  <button
                    className="btn-secondary"
                    type="button"
                    disabled={unlinkMutation.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Odpiąć powiązanie? Przelew i jego postingi pozostaną bez zmian.",
                        )
                      )
                        unlinkMutation.mutate(
                          { loanId, linkId: payment.id },
                          { onSuccess: () => setOffset(0) },
                        );
                    }}
                  >
                    Odepnij
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {loanApiErrorMessage(unlinkMutation.error) ? (
            <p role="alert" className="mt-2 text-sm text-red-400">
              {loanApiErrorMessage(unlinkMutation.error)}
            </p>
          ) : null}
        </section>
      ) : null}
    </article>
  );
}

export function FinanceLoans() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const accounts = useAccounts();
  const loans = useLoans();
  const activeLoanId = selectedId ?? loans.data?.[0]?.id ?? null;
  const detail = useLoan(activeLoanId);
  const updateLoan = useUpdateLoan();
  return (
    <div className="max-w-6xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-white">
          Kredyty i pożyczki
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Harmonogram jest planem. Powiązania wskazują istniejące przelewy i nie
          zmieniają księgi.
        </p>
      </header>
      <QueryFeedback
        loading={accounts.isLoading || loans.isLoading}
        error={accounts.isError || loans.isError}
        errorMessage="Nie udało się pobrać umów lub kont."
        onRetry={() => {
          void accounts.refetch();
          void loans.refetch();
        }}
      >
        <LoanAgreementForm
          accounts={accounts.data ?? []}
          onSuccess={setSelectedId}
        />
        {(loans.data?.length ?? 0) === 0 ? (
          <p className="card text-sm text-gray-400">
            Brak umów. Dodaj umowę, aby ręcznie wprowadzić harmonogram.
          </p>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[16rem_1fr]">
            <aside className="card h-fit">
              <h2 className="mb-3 font-semibold text-white">Umowy</h2>
              <div className="space-y-2">
                {loans.data?.map((loan) => (
                  <button
                    key={loan.id}
                    type="button"
                    className={`w-full rounded-md p-3 text-left text-sm ${loan.id === activeLoanId ? "bg-advisor-700 text-white" : "bg-gray-800 text-gray-300"}`}
                    onClick={() => setSelectedId(loan.id)}
                  >
                    {loan.name}
                    <span className="mt-1 block text-xs opacity-80">
                      {loan.is_active ? "Aktywna" : "Archiwalna"}
                    </span>
                  </button>
                ))}
              </div>
            </aside>
            <QueryFeedback
              loading={detail.isLoading}
              error={detail.isError}
              errorMessage="Nie udało się pobrać szczegółów umowy."
              onRetry={detail.refetch}
            >
              <main>
                {detail.data ? (
                  <>
                    <section className="card mb-4">
                      <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-semibold text-white">
                            {detail.data.name}
                          </h2>
                          <p className="mt-1 text-sm text-amber-200">
                            Plan ≠ wykonana płatność. Saldo księgowe nie jest
                            potwierdzonym pozostałym kapitałem.
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            className="btn-secondary"
                            type="button"
                            disabled={updateLoan.isPending}
                            onClick={() => {
                              const name = window.prompt(
                                "Nowa nazwa umowy",
                                detail.data.name,
                              );
                              if (name?.trim())
                                updateLoan.mutate({
                                  id: detail.data.id,
                                  name: name.trim(),
                                });
                            }}
                          >
                            Zmień nazwę
                          </button>
                          <button
                            className="btn-secondary"
                            type="button"
                            disabled={updateLoan.isPending}
                            onClick={() =>
                              updateLoan.mutate({
                                id: detail.data.id,
                                is_active: !detail.data.is_active,
                              })
                            }
                          >
                            {detail.data.is_active
                              ? "Archiwizuj umowę"
                              : "Przywróć umowę"}
                          </button>
                        </div>
                      </div>
                      <dl className="mt-4 grid gap-3 sm:grid-cols-3">
                        <div>
                          <dt className="text-sm text-gray-500">
                            Saldo księgowe
                          </dt>
                          <dd className="font-mono text-white">
                            {formatPLN(detail.data.ledger_balance_pln)} PLN
                          </dd>
                        </div>
                        <div>
                          <dt className="text-sm text-gray-500">
                            Plan łącznie
                          </dt>
                          <dd className="font-mono text-white">
                            {formatPLN(detail.data.total_planned_pln)} PLN
                          </dd>
                        </div>
                        <div>
                          <dt className="text-sm text-gray-500">
                            Do pokrycia w harmonogramie
                          </dt>
                          <dd className="font-mono text-white">
                            {formatPLN(detail.data.remaining_pln)} PLN
                          </dd>
                        </div>
                      </dl>
                      <p className="mt-3 text-xs text-gray-500">
                        Nie dodajemy rat do prognozy płynności, aby nie
                        zdublować obecnych harmonogramów.
                      </p>
                    </section>
                    <LoanInstallmentForm
                      key={activeLoanId}
                      loanId={detail.data.id}
                      onSuccess={() => setSelectedId(detail.data!.id)}
                    />
                    {loanApiErrorMessage(updateLoan.error) ? (
                      <p role="alert" className="mb-4 text-sm text-red-400">
                        {loanApiErrorMessage(updateLoan.error)}
                      </p>
                    ) : null}
                    <section className="card">
                      <h2 className="text-lg font-semibold text-white">Raty</h2>
                      {detail.data.installments.length === 0 ? (
                        <p className="mt-3 text-sm text-gray-400">
                          Brak rat. To nie oznacza, że kredyt został spłacony.
                        </p>
                      ) : (
                        detail.data.installments.map((installment) => (
                          <InstallmentRow
                            key={installment.id}
                            loanId={detail.data!.id}
                            installment={installment}
                          />
                        ))
                      )}
                    </section>
                  </>
                ) : (
                  <p className="card text-sm text-gray-400">
                    Brak danych szczegółowych umowy.
                  </p>
                )}
              </main>
            </QueryFeedback>
          </div>
        )}
      </QueryFeedback>
    </div>
  );
}
