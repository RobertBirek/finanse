import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
import { PageHeader } from "../components/PageHeader";
import { LoanAgreementForm } from "../components/finance/loans/LoanAgreementForm";
import { LoanInstallmentForm } from "../components/finance/loans/LoanInstallmentForm";
import { ScheduleHistory } from "../components/finance/loans/ScheduleHistory";
import { formatPLN } from "../lib/format";

const statusLabels: Record<LoanPaymentStatus, string> = {
  unpaid: "Niepokryta",
  partial: "Częściowo pokryta",
  paid: "Pokryta",
};

function InstallmentRow({
  loanId,
  installment,
  managed = false,
  configure,
}: {
  loanId: string;
  installment: LoanInstallment;
  managed?: boolean;
  configure: boolean;
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
            {installment.bank_number != null ? (
              <span className="text-sm font-normal">
                · numer bankowy w wersji: {installment.bank_number}{" "}
              </span>
            ) : null}
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
        {configure && installment.payments.length === 0 && !managed ? (
          <button
            className="btn-secondary"
            type="button"
            onClick={() => setEditing(true)}
          >
            Edytuj ratę
          </button>
        ) : null}
        {!configure ? (
          <button
            className="btn-secondary"
            type="button"
            onClick={() => setShowPayments((visible) => !visible)}
          >
            {showPayments ? "Ukryj płatności" : "Powiąż płatność"}
          </button>
        ) : null}
        {configure && installment.payments.length === 0 && !managed ? (
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

export function LoanDetails({
  loanId,
  configure = false,
}: {
  loanId: string;
  configure?: boolean;
}) {
  const detail = useLoan(loanId);
  const updateLoan = useUpdateLoan();
  const [paymentFilter, setPaymentFilter] = useState<LoanPaymentStatus | "all">(
    "all",
  );
  const visibleInstallments =
    detail.data?.installments
      .filter(
        (installment) =>
          paymentFilter === "all" ||
          installment.payment_status === paymentFilter,
      )
      .sort((a, b) => a.due_date.localeCompare(b.due_date)) ?? [];
  const installmentsByYear = visibleInstallments.reduce<
    Record<string, LoanInstallment[]>
  >((groups, installment) => {
    const year = installment.due_date.slice(0, 4);
    (groups[year] ??= []).push(installment);
    return groups;
  }, {});
  return (
    <QueryFeedback
      loading={detail.isLoading}
      error={detail.isError}
      errorMessage="Nie udało się pobrać szczegółów umowy."
      onRetry={detail.refetch}
    >
      <div className="min-w-0">
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
                <div className="flex flex-wrap gap-2">
                  {configure ? (
                    <>
                      {detail.data.is_active ? (
                        <Link
                          className="btn-secondary"
                          to={`/finances/imports?kind=loan_schedule&loan=${encodeURIComponent(detail.data.id)}`}
                        >
                          Importuj harmonogram
                        </Link>
                      ) : null}
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
                    </>
                  ) : (
                    <Link
                      className="btn-secondary"
                      to={`/settings/finances/loans?loan=${encodeURIComponent(detail.data.id)}`}
                    >
                      Ustawienia umowy
                    </Link>
                  )}
                </div>
              </div>
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <div>
                  <dt className="text-sm text-gray-500">Saldo księgowe</dt>
                  <dd className="font-mono text-white">
                    {formatPLN(detail.data.ledger_balance_pln)} PLN
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">
                    Kapitał w harmonogramie
                  </dt>
                  <dd className="font-mono text-white">
                    {formatPLN(detail.data.planned_principal_pln)} PLN
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">
                    Odsetki w harmonogramie
                  </dt>
                  <dd className="font-mono text-white">
                    {formatPLN(detail.data.planned_interest_pln)} PLN
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">
                    Opłaty w harmonogramie
                  </dt>
                  <dd className="font-mono text-white">
                    {formatPLN(detail.data.planned_fees_pln)} PLN
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Powiązane spłaty</dt>
                  <dd className="font-mono text-white">
                    {formatPLN(detail.data.paid_pln)} PLN
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Plan łącznie</dt>
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
                Nie dodajemy rat do prognozy płynności, aby nie zdublować
                obecnych harmonogramów.
              </p>
            </section>
            {configure ? (
              detail.data.active_schedule_revision_id ? (
                <p className="card mb-4 text-sm">
                  Plan z wersją bankową jest niezmienny. Zamiast edytować raty w
                  miejscu, importuj nowy harmonogram. Powiązania płatności
                  pozostają dostępne.
                </p>
              ) : (
                <details className="card mb-4">
                  <summary className="cursor-pointer font-semibold text-white">
                    Dodaj ratę ręcznie
                  </summary>
                  <LoanInstallmentForm
                    key={detail.data.id}
                    loanId={detail.data.id}
                    onSuccess={() => {}}
                  />
                </details>
              )
            ) : null}
            {loanApiErrorMessage(updateLoan.error) ? (
              <p role="alert" className="mb-4 text-sm text-red-400">
                {loanApiErrorMessage(updateLoan.error)}
              </p>
            ) : null}
            <section className="card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-white">Raty</h2>
                <label className="text-sm text-gray-400">
                  Status
                  <select
                    className="input ml-2"
                    value={paymentFilter}
                    onChange={(event) =>
                      setPaymentFilter(
                        event.target.value as LoanPaymentStatus | "all",
                      )
                    }
                  >
                    <option value="all">Wszystkie</option>
                    {Object.entries(statusLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {detail.data.installments.length === 0 ? (
                <p className="mt-3 text-sm text-gray-400">
                  Brak rat. To nie oznacza, że kredyt został spłacony.
                </p>
              ) : visibleInstallments.length === 0 ? (
                <p className="mt-3 text-sm text-gray-400">
                  Brak rat o wybranym statusie.
                </p>
              ) : (
                Object.entries(installmentsByYear).map(
                  ([year, installments]) => (
                    <section key={year} aria-label={`Raty ${year}`}>
                      <h3 className="mt-4 text-sm font-semibold text-gray-300">
                        {year}
                      </h3>
                      {installments.map((installment) => (
                        <InstallmentRow
                          key={installment.id}
                          loanId={detail.data!.id}
                          installment={installment}
                          configure={configure}
                          managed={!!detail.data!.active_schedule_revision_id}
                        />
                      ))}
                    </section>
                  ),
                )
              )}
            </section>
            <ScheduleHistory
              key={`history:${detail.data.id}`}
              loanId={detail.data.id}
            />
          </>
        ) : (
          <p className="card text-sm text-gray-400">
            Brak danych szczegółowych umowy.
          </p>
        )}
      </div>
    </QueryFeedback>
  );
}

export function FinanceLoanSettings() {
  const [params, setParams] = useSearchParams();
  const [locallySelectedLoanId, setLocallySelectedLoanId] = useState<
    string | undefined
  >();
  const accounts = useAccounts();
  const loans = useLoans();
  const requestedLoanId = params.get("loan");
  const selectedLoan = loans.data?.find((loan) => loan.id === requestedLoanId);
  const isLocallySelected = requestedLoanId === locallySelectedLoanId;
  const loanId =
    selectedLoan?.id ??
    (isLocallySelected
      ? requestedLoanId
      : requestedLoanId === null
        ? loans.data?.[0]?.id
        : undefined);
  const unavailableSelection =
    requestedLoanId !== null &&
    loans.data !== undefined &&
    !loans.isLoading &&
    !loans.isError &&
    !selectedLoan &&
    !isLocallySelected;
  function select(id: string) {
    setLocallySelectedLoanId(id);
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("loan", id);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ustawienia kredytów i pożyczek"
        actions={
          <Link
            className="btn-secondary"
            to={`/finances/loans${loanId ? `?loan=${encodeURIComponent(loanId)}` : ""}`}
          >
            Przejdź do kredytów i pożyczek
          </Link>
        }
      />
      <div className="flex gap-4">
        <Link className="underline" to="/settings/finances/loans/allegro-pay">
          Ustawienia Allegro Pay
        </Link>
        <Link className="underline" to="/settings/finances/cards">
          Ustawienia kart kredytowych
        </Link>
      </div>
      <QueryFeedback
        loading={loans.isLoading}
        error={loans.isError}
        errorMessage="Nie udało się pobrać umów."
        onRetry={loans.refetch}
      >
        <details className="card">
          <summary className="cursor-pointer font-semibold text-white">
            Dodaj umowę
          </summary>
          <QueryFeedback
            loading={accounts.isLoading}
            error={accounts.isError}
            errorMessage="Nie udało się pobrać kont. Istniejące umowy pozostają dostępne."
            onRetry={accounts.refetch}
          >
            <LoanAgreementForm
              accounts={accounts.data ?? []}
              onSuccess={select}
            />
          </QueryFeedback>
        </details>
        {loans.data?.length ? (
          <>
            {unavailableSelection ? (
              <p role="alert" className="text-sm text-amber-200">
                Wybrana umowa nie jest dostępna. Wybierz umowę z listy.
              </p>
            ) : null}
            <label className="block">
              Umowa
              <select
                className="input"
                value={loanId ?? ""}
                onChange={(event) => select(event.target.value)}
              >
                {unavailableSelection ? (
                  <option value="" disabled>
                    Wybierz dostępną umowę
                  </option>
                ) : null}
                {loans.data.map((loan) => (
                  <option key={loan.id} value={loan.id}>
                    {loan.name}
                    {loan.is_active ? "" : " · Archiwalna"}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <p>Brak umów.</p>
        )}
        {loanId ? <LoanDetails key={loanId} loanId={loanId} configure /> : null}
      </QueryFeedback>
    </div>
  );
}
