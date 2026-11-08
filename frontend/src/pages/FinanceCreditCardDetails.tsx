import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAccounts, useCategories } from "../api/finance";
import { useCreditCard, type CreditCard } from "../api/creditCards";
import { CardForm, type CardField } from "../components/finance/CardForm";
import { CardPlanDetails } from "../components/finance/CardPlanDetails";
import { CardAllocations } from "../components/finance/CardAllocations";
import { CardEstimate } from "../components/finance/CardEstimate";
import { CardRemoveRecord } from "../components/finance/CardRemoveRecord";
import { formatPLN } from "../lib/format";

const money = (name: string, label: string, value?: number): CardField => ({
  name,
  label,
  type: "money",
  value: value === undefined ? undefined : String(value / 100),
});
const integer = (name: string, label: string, value?: number): CardField => ({
  name,
  label,
  type: "integer",
  value,
});

function CardDetails({
  accountId,
  card,
}: {
  accountId: string;
  card: CreditCard;
}) {
  const categories = useCategories();
  const [chargeMode, setChargeMode] = useState("");
  const expenseOptions = (categories.data ?? [])
    .filter((item) => item.type === "expense" && item.is_active)
    .map((item) => ({ value: item.id, label: item.name }));
  const targetOptions = [
    ...card.statements.map((item) => ({
      value: `statement:${item.id}`,
      label: `Wyciąg do ${item.period_end}`,
    })),
    ...card.plans
      .filter((item) => item.status === "active")
      .map((item) => ({ value: `plan:${item.id}`, label: item.name })),
  ];
  return (
    <div className="space-y-6">
      <section aria-label="Wykorzystanie limitu" className="card">
        <dl className="grid grid-cols-1 gap-5 sm:grid-cols-3">
          {[
            ["Limit", card.limit_pln],
            ["Zadłużenie zaksięgowane", card.debt_pln],
            ["Dostępny limit", card.available_pln],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-sm text-gray-400">{label}</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums text-white">
                {formatPLN(Number(value))} PLN
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 flex flex-wrap gap-4 border-t border-gray-700 pt-3 text-sm text-gray-300">
          <span>Rezerwacje: {formatPLN(card.pending_debits_pln)} PLN</span>
          <span>Nadpłata: {formatPLN(card.overpayment_pln)} PLN</span>
          {card.overlimit_pln > 0 ? (
            <strong className="text-red-300">
              Przekroczenie: {formatPLN(card.overlimit_pln)} PLN
            </strong>
          ) : null}
        </div>
        <p className="mt-3 text-sm text-gray-400">
          Oprocentowanie karty: {card.apr}% rocznie. Maksymalny okres
          bezodsetkowy: {card.grace_days} dni — zależy od warunków banku i
          terminowej pełnej spłaty; nie jest gwarancją dla każdej transakcji.
        </p>
        <p className="mt-2 text-sm text-gray-400">
          Kapitał planów jest już w saldzie księgi — nie dodajemy go drugi raz.
          Dostępny limit uwzględnia rezerwacje, ale nie zwiększa się o nadpłatę.
        </p>
      </section>
      <section className="card space-y-3">
        <h2 className="text-lg font-semibold text-white">
          Wyciągi i terminy spłaty
        </h2>
        {card.statements.length === 0 ? (
          <p>Dodaj wyciąg bankowy, aby uzgodnić saldo i termin spłaty.</p>
        ) : (
          card.statements.map((item) => (
            <article
              key={item.id}
              className="rounded border border-gray-700 p-3 text-sm"
            >
              <h3 className="font-semibold text-white">
                Wyciąg do {item.period_end}
              </h3>
              <p>
                Termin bankowy: <time>{item.due_date}</time>
              </p>
              <p>
                Zadłużenie na wyciągu: {formatPLN(item.debt_pln)} PLN ·
                Pozostało do spłaty: {formatPLN(item.remaining_pln)} PLN
              </p>
              <p>
                Minimum: {formatPLN(item.minimum_pln)} PLN · Brakuje do minimum:{" "}
                {formatPLN(item.minimum_remaining_pln)} PLN
              </p>
              <p
                className={
                  item.reconciliation_difference_pln === 0
                    ? "text-green-400"
                    : "text-red-400"
                }
              >
                Różnica księga − wyciąg:{" "}
                {formatPLN(item.reconciliation_difference_pln)} PLN
              </p>
              <CardRemoveRecord
                accountId={accountId}
                path={`/statements/${item.id}`}
                label="Usuń błędny wyciąg (bez zmiany księgi)"
              />
            </article>
          ))
        )}
        <p className="text-xs text-gray-400">
          Wyciąg opisuje historyczny stan, nie saldo dzisiejsze. Data bankowa ma
          pierwszeństwo przed domyślnym dniem spłaty.
        </p>
      </section>
      <CardForm
        accountId={accountId}
        title="Dodaj wyciąg"
        path="/statements"
        fields={[
          { name: "period_start", label: "Początek okresu", type: "date" },
          { name: "period_end", label: "Koniec okresu", type: "date" },
          { name: "due_date", label: "Termin spłaty z wyciągu", type: "date" },
          money("debt_pln", "Zadłużenie z wyciągu PLN"),
          money("minimum_pln", "Minimalna spłata PLN"),
          { name: "source_reference", label: "Źródło / nazwa wyciągu" },
        ]}
      />
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-white">Plany ratalne</h2>
        {card.plans.length === 0 ? (
          <p className="card text-gray-400">
            Brak zarejestrowanych planów. Zamknięte historyczne plany nie są
            automatycznie odtwarzane.
          </p>
        ) : (
          card.plans.map((plan) => (
            <CardPlanDetails
              key={`${plan.id}:${plan.version}`}
              accountId={accountId}
              plan={plan}
            />
          ))
        )}
      </section>
      <CardForm
        accountId={accountId}
        title="Nowy plan ratalny"
        path="/plans"
        submitLabel="Utwórz plan i szacunkowy harmonogram"
        fields={[
          { name: "name", label: "Nazwa planu" },
          {
            name: "source_transaction_id",
            label: "Transakcja źródłowa",
            candidates: "source",
          },
          money("principal_pln", "Kapitał PLN"),
          { name: "apr", label: "Oprocentowanie planu %", type: "decimal" },
          integer("count", "Liczba rat"),
          { name: "first_due", label: "Pierwsza rata", type: "date" },
          money("fees_pln", "Prowizja PLN", 0),
        ]}
      >
        <p className="text-sm text-gray-400">
          Wybierz zaksięgowany zakup lub wypłatę z karty. Przy nowym
          finansowaniu najpierw zapisz rzeczywisty przelew. Plan nie tworzy
          kolejnego wydatku. Szacunek: równy kapitał, odsetki APR/12;
          harmonogram bankowy ma pierwszeństwo.
        </p>
      </CardForm>
      <CardAllocations
        accountId={accountId}
        card={card}
        targets={targetOptions}
      />
      <label className="block text-sm text-gray-300">
        Sposób zapisania kosztu
        <select
          aria-label="Sposób zapisania kosztu"
          className="input mt-1 w-full"
          value={chargeMode}
          onChange={(event) => setChargeMode(event.target.value)}
        >
          <option value="">Wybierz sposób rozliczenia</option>
          <option value="new">Zaksięguj nowy koszt lub zwrot</option>
          <option value="link">
            Powiąż koszt lub zwrot już obecny w księdze
          </option>
        </select>
      </label>
      {categories.isError ? (
        <p role="alert">Nie udało się pobrać kategorii kosztów.</p>
      ) : chargeMode ? (
        <CardForm
          key={chargeMode}
          accountId={accountId}
          title="Odsetki, opłaty i korekty"
          path="/charges"
          submitLabel="Zapisz rozliczenie kosztu"
          fields={[
            {
              name: "kind",
              label: "Rodzaj kosztu",
              options: [
                { value: "interest", label: "Odsetki" },
                { value: "fee", label: "Opłata" },
                { value: "interest_refund", label: "Zwrot odsetek" },
                { value: "fee_refund", label: "Zwrot opłaty" },
              ],
            },
            money("amount_pln", "Kwota PLN"),
            { name: "booking_date", label: "Data księgowania", type: "date" },
            {
              name: "category_id",
              label: "Kategoria kosztu",
              options: expenseOptions,
            },
            { name: "description", label: "Opis" },
            {
              name: "plan_id",
              label: "Plan (opcjonalnie)",
              optional: true,
              options: card.plans.map((item) => ({
                value: item.id,
                label: item.name,
              })),
            },
            ...(chargeMode === "link"
              ? [
                  {
                    name: "existing_transaction_id",
                    label: "Istniejąca transakcja kosztu",
                    candidates: "charge" as const,
                  },
                ]
              : []),
          ]}
        >
          <p className="text-sm text-gray-400">
            Wybierz istniejący zapis, jeśli koszt jest już w księdze. Bez wyboru
            zostanie utworzona nowa transakcja. Zwrot zmniejsza koszt, nie
            przychód. Nie wpisuj tu prognozowanych odsetek.
          </p>
        </CardForm>
      ) : null}
      <CardEstimate key={card.apr} accountId={accountId} apr={card.apr} />
      <section className="card">
        <h3 className="font-semibold text-white">
          Zaksięgowane koszty i korekty
        </h3>
        {card.charges.length === 0 ? (
          <p className="text-sm text-gray-400">Brak przypisanych kosztów.</p>
        ) : (
          card.charges.map((item) => (
            <div key={item.id} className="mt-3 text-sm">
              {item.booking_date} · {item.description} ·{" "}
              {item.kind.endsWith("_refund") ? "−" : ""}
              {formatPLN(item.amount_pln)} PLN
              <CardRemoveRecord
                accountId={accountId}
                path={`/charges/${item.id}`}
                label="Cofnij opis kosztu (transakcja pozostanie)"
              />
            </div>
          ))
        )}
      </section>
    </div>
  );
}

export function FinanceCreditCardDetails() {
  const accounts = useAccounts();
  const { accountId = "" } = useParams();
  const query = useCreditCard(accountId);
  const account = accounts.data?.find((item) => item.id === accountId);
  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/settings/finances/cards"
            className="text-sm text-advisor-700 underline"
          >
            Wszystkie karty
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-white">
            Wyciągi i raty{account ? ` — ${account.name}` : ""}
          </h1>
        </div>
        <Link
          className="btn-secondary"
          to={`/settings/finances/accounts?edit=${encodeURIComponent(accountId)}`}
        >
          Edytuj konto
        </Link>
      </div>
      {query.isLoading || accounts.isLoading ? (
        <p role="status">Ładowanie karty…</p>
      ) : query.isError || accounts.isError ? (
        <p role="alert">
          Nie udało się pobrać karty. Odśwież dane przed zapisem.
        </p>
      ) : query.data ? (
        <fieldset
          key={accountId}
          disabled={!account?.is_active}
          className="min-w-0"
        >
          {account && !account.is_active ? (
            <p className="mb-4 text-sm text-gray-400">
              Karta nieaktywna — rozliczenia są dostępne tylko do odczytu.
            </p>
          ) : null}
          <CardDetails accountId={accountId} card={query.data} />
        </fieldset>
      ) : (
        <p className="card text-gray-400">
          Nie znaleziono skonfigurowanej karty. Uzupełnij warunki w edycji konta
          lub wróć do listy kart.
        </p>
      )}
    </div>
  );
}
