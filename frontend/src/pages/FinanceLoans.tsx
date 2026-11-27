import { useQueries } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useAllegroPay } from "../api/allegroPay";
import { useCreditCards, type CreditCard } from "../api/creditCards";
import { useCardStatementPlans, useLoans } from "../api/loans";
import { CardAllocations } from "../components/finance/CardAllocations";
import { CardPlanDetails } from "../components/finance/CardPlanDetails";
import { StatementPlan } from "../components/finance/loans/StatementPlan";
import { PageHeader } from "../components/PageHeader";
import api from "../lib/api";
import { formatCalendarDate } from "../lib/date";
import { colorInk, entityColor } from "../lib/financeColors";
import { AllegroPayDetails } from "./FinanceAllegroPay";
import { LoanDetails } from "./FinanceLoanSettings";

const selectionKeys = ["loan", "allegro", "cardPlan", "statementPlan"] as const;
type Selection = (typeof selectionKeys)[number];
type Tile = {
  kind: Selection;
  id: string;
  title: string;
  label: string;
  detail: () => React.ReactNode;
};
const settings = "/settings/finances/loans";

export function FinanceLoans() {
  const [params, setParams] = useSearchParams();
  const loans = useLoans();
  const allegro = useAllegroPay();
  const statements = useCardStatementPlans();
  const cards = useCreditCards();
  const configured = (cards.data ?? []).filter((card) => card.configured);
  const cardDetails = useQueries({
    queries: configured.map(({ account_id }) => ({
      queryKey: ["finance", "credit-card", account_id],
      queryFn: async ({ signal }) =>
        (
          await api.get<CreditCard>(
            `/finance/accounts/${account_id}/credit-card`,
            { signal },
          )
        ).data,
    })),
  });

  const selection = selectionKeys.find((key) => params.has(key));
  const selectedId = selection ? params.get(selection) : null;
  const tiles: Tile[] = [
    ...(loans.data ?? []).map((loan): Tile => ({
      kind: "loan",
      id: loan.id,
      title: loan.name,
      label: loan.is_active ? "Umowa aktywna" : "Umowa archiwalna",
      detail: () => <LoanDetails loanId={loan.id} />,
    })),
    ...(allegro.data ?? []).map((profile): Tile => ({
      kind: "allegro",
      id: profile.id,
      title: profile.account_name,
      label: "Allegro Pay",
      detail: () => <AllegroPayDetails profile={profile} />,
    })),
    ...cardDetails.flatMap(({ data }, index) => {
      const card = configured[index];
      if (!data) return [];
      return data.plans.map((plan): Tile => ({
        kind: "cardPlan",
        id: plan.id,
        title: plan.name,
        label: `${card.name} · ${plan.status === "active" ? "Plan karty" : "Plan zamknięty"}`,
        detail: () => (
          <div className="space-y-4">
            <CardPlanDetails
              accountId={card.account_id}
              plan={plan}
              configure={false}
            />
            <CardAllocations
              accountId={card.account_id}
              card={data}
              fixedPlanId={plan.id}
              targets={
                plan.status === "active"
                  ? [{ value: `plan:${plan.id}`, label: plan.name }]
                  : []
              }
            />
            <Link
              className="btn-secondary"
              to={`/settings/finances/cards/${encodeURIComponent(card.account_id)}`}
            >
              Ustawienia karty i harmonogramu
            </Link>
          </div>
        ),
      }));
    }),
    ...(statements.data ?? [])
      .slice()
      .sort((a, b) => b.period_end.localeCompare(a.period_end))
      .map((item): Tile => {
        const title =
          item.breakdown.installment_original_principal_pln == null
            ? "Pozycje rat z wyciągu Velo"
            : "Plan „Komfort” z wyciągu Velo";
        return {
          kind: "statementPlan",
          id: item.source_id,
          title,
          label: `Wyciąg · ${formatCalendarDate(item.period_end)}`,
          detail: () => <StatementPlan item={item} title={title} />,
        };
      }),
  ];

  const selected = tiles.find(
    ({ kind, id }) => kind === selection && id === selectedId,
  );
  const sources = [
    { name: "umów", queries: [loans] },
    { name: "Allegro Pay", queries: [allegro] },
    { name: "planów kart", queries: [cards, ...cardDetails] },
    { name: "planów z wyciągów", queries: [statements] },
  ];
  const loading = sources.some(({ queries }) =>
    queries.some((query) => query.isLoading),
  );
  const error = sources.some(({ queries }) =>
    queries.some((query) => query.isError),
  );

  function toggle(tile: Tile) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        selectionKeys.forEach((key) => next.delete(key));
        if (tile !== selected) next.set(tile.kind, tile.id);
        return next;
      },
      { preventScrollReset: true },
    );
  }

  return (
    <div className="page-workspace">
      <PageHeader
        title="Kredyty i pożyczki"
        actions={
          <Link className="btn-secondary" to={settings}>
            Ustawienia kredytów i pożyczek
          </Link>
        }
      />
      <section className="my-6" aria-label="Wybór zobowiązania">
        <div className="finance-account-strip px-1 py-1">
          {tiles.map((tile) => {
            const key = `${tile.kind}:${tile.id}`;
            const color = entityColor(key);
            return (
              <button
                key={key}
                type="button"
                className="finance-account-chip finance-account-filter"
                style={{ borderColor: color }}
                aria-pressed={tile === selected}
                onClick={() => toggle(tile)}
              >
                <span
                  aria-hidden="true"
                  className="finance-bank-mark"
                  style={{ backgroundColor: color, color: colorInk(color) }}
                >
                  {tile.title.slice(0, 1).toUpperCase()}
                </span>
                <span>
                  <small>{tile.label}</small>
                  <strong>{tile.title}</strong>
                </span>
              </button>
            );
          })}
        </div>
        {loading ? <p role="status">Ładowanie zobowiązań…</p> : null}
        {sources.map(({ name, queries }) =>
          queries.some((query) => query.isError) ? (
            <p role="alert" key={name}>
              Nie udało się pobrać danych dla {name}.{" "}
              <button
                type="button"
                className="underline"
                onClick={() => {
                  queries
                    .filter((query) => query.isError)
                    .forEach((query) => void query.refetch());
                }}
              >
                Ponów
              </button>
            </p>
          ) : null,
        )}
      </section>
      {selected ? (
        <section
          key={`${selected.kind}:${selected.id}`}
          aria-label={`Szczegóły: ${selected.title}`}
        >
          {selected.detail()}
        </section>
      ) : selection && !loading ? (
        <p>Wybrane zobowiązanie jest niedostępne. Wybierz inny kafelek.</p>
      ) : tiles.length && !selection ? (
        <p>Wybierz kredyt lub pożyczkę.</p>
      ) : !loading && !error ? (
        <p>
          Brak zobowiązań.{" "}
          <Link className="underline" to={settings}>
            Dodaj umowę w Ustawieniach
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
