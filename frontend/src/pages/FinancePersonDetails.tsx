import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  personError,
  usePerson,
  usePersonGifts,
  usePersonSummary,
  useUpdatePerson,
} from "../api/people";
import { useAccounts } from "../api/finance";
import { PersonEditor } from "../components/finance/PersonEditor";
import { PersonGiftDialog } from "../components/finance/PersonGiftDialog";
import { TransactionDateLabel } from "../components/finance/TransactionDateLabel";
import { QueryFeedback } from "../components/QueryFeedback";
import { formatPLN } from "../lib/format";

export function FinancePersonDetails() {
  const { personId = "" } = useParams();
  return <PersonDetails key={personId} personId={personId} />;
}
function PersonDetails({ personId }: { personId: string }) {
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState(false);
  const [transactionId, setTransactionId] = useState<string | null>(null);
  const person = usePerson(personId);
  const summary = usePersonSummary(personId);
  const gifts = usePersonGifts(personId, offset);
  const accounts = useAccounts();
  const update = useUpdatePerson();
  return (
    <div className="space-y-6">
      <Link className="text-advisor-400 underline" to="/finances/people">
        Wszystkie osoby
      </Link>
      <QueryFeedback
        loading={person.isLoading}
        error={person.isError}
        onRetry={person.refetch}
        errorMessage="Nie udało się pobrać osoby."
      >
        {person.data ? (
          <>
            <header className="flex flex-wrap justify-between gap-3">
              <div>
                <h1 className="text-2xl font-bold">{person.data.name}</h1>
                {!person.data.is_active ? (
                  <p>Osoba archiwalna — historia pozostaje dostępna.</p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-secondary"
                  onClick={() => setEditing(true)}
                >
                  Edytuj osobę
                </button>
                <button
                  className="btn-secondary"
                  disabled={update.isPending}
                  onClick={() =>
                    update.mutate({
                      id: personId,
                      expected_version: person.data!.version,
                      is_active: !person.data!.is_active,
                    })
                  }
                >
                  {person.data.is_active
                    ? "Archiwizuj osobę"
                    : "Przywróć osobę"}
                </button>
              </div>
            </header>
            {update.isError ? (
              <p role="alert" className="text-red-400">
                {personError(update.error)}{" "}
                <button
                  className="underline"
                  onClick={() => {
                    update.reset();
                    person.refetch();
                  }}
                >
                  Odśwież osobę
                </button>
              </p>
            ) : null}
            <section className="card">
              <h2 className="text-sm text-gray-400">Otrzymane darowizny</h2>
              <QueryFeedback
                loading={summary.isLoading}
                error={summary.isError}
                onRetry={summary.refetch}
                errorMessage="Nie udało się pobrać sumy darowizn."
              >
                {summary.data ? (
                  <>
                    <p className="text-3xl font-semibold tabular-nums mt-2">
                      {formatPLN(summary.data.received_gifts_pln)} PLN
                    </p>
                    <p className="text-sm text-gray-400 mt-2">
                      {summary.data.gift_count} operacji · cała przypisana
                      historia
                    </p>
                    {Object.entries(summary.data.received_by_currency)
                      .filter(([currency]) => currency !== "PLN")
                      .map(([currency, amount]) => (
                        <p key={currency} className="text-sm">
                          Kwota źródłowa: {formatPLN(amount)} {currency}
                        </p>
                      ))}
                  </>
                ) : null}
              </QueryFeedback>
              <p className="text-sm text-gray-400 mt-3">
                To historia przychodów na Twoich rachunkach, nie dodatkowe saldo
                ani dług.
              </p>
            </section>
            <section className="card">
              <h2 className="text-lg font-semibold mb-3">Historia darowizn</h2>
              <QueryFeedback
                loading={gifts.isLoading}
                error={gifts.isError}
                onRetry={gifts.refetch}
                errorMessage="Nie udało się pobrać historii darowizn."
              >
                {gifts.data?.items.length === 0 ? (
                  <p>
                    Brak przypisanych darowizn. Przypisz darczyńcę w szczegółach
                    przychodu.
                  </p>
                ) : null}
                <ul className="divide-y divide-gray-800">
                  {gifts.data?.items.map((txn) => {
                    const leg = txn.postings.find(
                      (p) => p.account_id && p.direction === "credit",
                    );
                    return (
                      <li
                        key={txn.id}
                        className="py-3 flex flex-wrap justify-between gap-3"
                      >
                        <div>
                          <p className="font-medium break-words">
                            {txn.effective_description || txn.description}
                          </p>
                          <p className="text-sm text-gray-400">
                            <TransactionDateLabel transaction={txn} /> ·{" "}
                            {accounts.data?.find(
                              (a) => a.id === leg?.account_id,
                            )?.name ?? "Konto odbiorcze"}
                          </p>
                          {txn.annotations?.display_description ? (
                            <p className="text-sm text-gray-400">
                              Oryginalny opis: {txn.description}
                            </p>
                          ) : null}
                        </div>
                        <div className="text-right">
                          <p className="tabular-nums">
                            {leg
                              ? `${formatPLN(leg.base_amount_pln)} PLN`
                              : "Kwota niedostępna"}
                          </p>
                          <button
                            className="text-advisor-400 underline text-sm"
                            onClick={() => setTransactionId(txn.id)}
                          >
                            Darczyńca i powiązanie
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <div className="flex flex-wrap gap-3 mt-4">
                  <button
                    className="btn-secondary"
                    disabled={!offset}
                    onClick={() => setOffset((v) => Math.max(0, v - 50))}
                  >
                    Poprzednia strona
                  </button>
                  <button
                    className="btn-secondary"
                    disabled={!gifts.data || offset + 50 >= gifts.data.total}
                    onClick={() => setOffset((v) => v + 50)}
                  >
                    Następna strona
                  </button>
                </div>
              </QueryFeedback>
            </section>
            {editing ? (
              <PersonEditor
                initial={person.data}
                onClose={() => setEditing(false)}
              />
            ) : null}
          </>
        ) : null}
      </QueryFeedback>
      {transactionId ? (
        <PersonGiftDialog
          key={transactionId}
          transactionId={transactionId}
          onClose={() => setTransactionId(null)}
        />
      ) : null}
    </div>
  );
}
