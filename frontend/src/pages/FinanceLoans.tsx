import { useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useAccounts } from "../api/finance";
import api from "../lib/api";
import { useCreditCards, type CreditCard } from "../api/creditCards";
import {
  loanApiErrorMessage,
  useDeleteLoanInstallment,
  useLinkLoanPayment,
  useLoan,
  useLoanPaymentCandidates,
  useLoans,
  useCardStatementPlans,
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
import { formatCalendarDate } from "../lib/date";

function CardPlans() {
  const cards = useCreditCards();
  const statements = useCardStatementPlans();
  const configured = (cards.data ?? []).filter((card) => card.configured);
  const details = useQueries({
    queries: configured.map((card) => ({
      queryKey: ["finance", "credit-card", card.account_id],
      queryFn: async () =>
        (
          await api.get<CreditCard>(
            `/finance/accounts/${card.account_id}/credit-card`,
          )
        ).data,
    })),
  });
  const failed =
    cards.isError || statements.isError || details.some((item) => item.isError);
  const loading =
    cards.isLoading ||
    statements.isLoading ||
    details.some((item) => item.isLoading);
  return (
    <section
      className="card mb-5 space-y-4"
      aria-labelledby="card-plans-heading"
    >
      <h2 id="card-plans-heading" className="text-xl font-semibold">
        Plany ratalne kart kredytowych
      </h2>
      <QueryFeedback
        loading={loading}
        error={failed}
        errorMessage="Nie udało się pobrać planów kart lub wyciągów."
        onRetry={() => {
          void cards.refetch();
          void statements.refetch();
          details.forEach((item) => void item.refetch());
        }}
      >
        {statements.data?.map((item) => (
          <article
            key={item.source_id}
            className="rounded-lg border border-gray-700 p-4 space-y-2"
          >
            <h3 className="font-semibold">
              {item.breakdown.installment_original_principal_pln == null
                ? "Pozycje rat z wyciągu Velo"
                : "Plan „Komfort” z wyciągu Velo"}
            </h3>
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
                  Rata {formatPLN(item.breakdown.komfort_installment.total_pln)}{" "}
                  PLN · kapitał{" "}
                  {formatPLN(item.breakdown.komfort_installment.principal_pln)}{" "}
                  PLN · odsetki{" "}
                  {formatPLN(item.breakdown.komfort_installment.interest_pln)}{" "}
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
                  {item.breakdown.unassigned_installment_charges.map(
                    (charge) => (
                      <li key={charge.row_key}>
                        {charge.kind === "principal" ? "Kapitał" : "Odsetki"} ·{" "}
                        {formatCalendarDate(charge.booking_date)} ·{" "}
                        {formatPLN(charge.amount_pln)} PLN
                      </li>
                    ),
                  )}
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
        ))}
        {details.flatMap((result, index) =>
          (result.data?.plans ?? []).map((plan) => (
            <article
              key={plan.id}
              className="rounded-lg border border-gray-700 p-4 space-y-2"
            >
              <h3 className="font-semibold">
                {plan.name} · {configured[index].name}
              </h3>
              <p>
                {plan.status === "active" ? "Aktywny" : "Zamknięty"} · Kwota
                planu {formatPLN(plan.principal_pln)} PLN · Pozostały kapitał{" "}
                {formatPLN(plan.remaining_principal_pln)} PLN
              </p>
              <p>
                Oprocentowanie {plan.apr}% ·{" "}
                {plan.schedule_kind === "bank"
                  ? "Harmonogram bankowy"
                  : "Harmonogram szacunkowy"}
              </p>
              <Link
                className="underline"
                to={`/settings/finances/cards/${encodeURIComponent(configured[index].account_id)}`}
              >
                Otwórz kartę i harmonogram
              </Link>
            </article>
          )),
        )}
        {!statements.data?.length &&
        !details.some((item) => item.data?.plans.length) ? (
          <p className="text-sm text-gray-400">
            Brak rozpoznanych planów ratalnych kart.
          </p>
        ) : null}
        {!!statements.data?.length &&
        details.some((item) => item.data?.plans.length) ? (
          <p className="text-sm text-gray-400">
            Wyciąg i zapisane plany mogą dotyczyć tego samego zobowiązania.
            Porównaj je przed sumowaniem.
          </p>
        ) : null}
      </QueryFeedback>
    </section>
  );
}

const statusLabels: Record<LoanPaymentStatus, string> = {
  unpaid: "Niepokryta",
  partial: "Częściowo pokryta",
  paid: "Pokryta",
};

function InstallmentRow({
  loanId,
  installment,
  managed = false,
}: {
  loanId: string;
  installment: LoanInstallment;
  managed?: boolean;
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
        {installment.payments.length === 0 && !managed ? (
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
        {installment.payments.length === 0 && !managed ? (
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
  const [params] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    params.get("loan"),
  );
  const accounts = useAccounts();
  const loans = useLoans();
  const activeLoanId = selectedId ?? loans.data?.[0]?.id ?? null;
  const detail = useLoan(activeLoanId);
  const updateLoan = useUpdateLoan();
  return (
    <div className="page-workspace">
      <PageHeader
        title="Kredyty i pożyczki"
        description="Harmonogram jest planem. Powiązania wskazują istniejące przelewy i nie zmieniają księgi."
      />
      <CardPlans />
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
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[16rem_1fr]">
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
              <main className="min-w-0">
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
                        </div>
                      </div>
                      <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
                          <dt className="text-sm text-gray-500">
                            Powiązane spłaty
                          </dt>
                          <dd className="font-mono text-white">
                            {formatPLN(detail.data.paid_pln)} PLN
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
                    {detail.data.active_schedule_revision_id ? (
                      <p className="card mb-4 text-sm">
                        Plan z wersją bankową jest niezmienny. Zamiast edytować
                        raty w miejscu, importuj nowy harmonogram. Powiązania
                        płatności pozostają dostępne.
                      </p>
                    ) : (
                      <LoanInstallmentForm
                        key={activeLoanId}
                        loanId={detail.data.id}
                        onSuccess={() => setSelectedId(detail.data!.id)}
                      />
                    )}
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
                            managed={!!detail.data!.active_schedule_revision_id}
                          />
                        ))
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
              </main>
            </QueryFeedback>
          </div>
        )}
      </QueryFeedback>
    </div>
  );
}
