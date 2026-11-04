import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useCategoryProposals,
  useSuggestionActivity,
} from "../api/categoryProposals";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { ProposalReview } from "../components/finance/ProposalReview";
import { useAuthStore } from "../stores/authStore";

export function FinanceCategoryProposals() {
  const session = useAuthStore((s) => s.sessionVersion);
  return <Queue key={session} />;
}
function Queue() {
  const [cursor, setCursor] = useState<string | null>(null);
  const proposals = useCategoryProposals(cursor);
  const activity = useSuggestionActivity();
  return (
    <div className="max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold">Propozycje kategorii</h1>
      <FinanceTabs />
      <p className="mb-5 text-sm text-gray-400">
        Nie filtrujemy tej kolejki według miesiąca. AI tylko proponuje — decyzja
        o kategorii należy do Ciebie.{" "}
        <Link className="underline" to="/settings/finances/categorization">
          Ustawienia zgody i limity
        </Link>
      </p>
      {proposals.isLoading ? (
        <p role="status">Wczytywanie propozycji…</p>
      ) : null}
      {proposals.isError ? (
        <div role="alert" className="card mb-4">
          <p>Nie udało się pobrać propozycji.</p>
          <button
            type="button"
            className="btn-secondary mt-3"
            onClick={() => void proposals.refetch()}
          >
            Spróbuj ponownie
          </button>
        </div>
      ) : null}
      {proposals.isSuccess && !proposals.data.items.length ? (
        <p className="card mb-4">Brak propozycji do przejrzenia.</p>
      ) : null}
      {activity.data?.active_jobs.length ? (
        <p role="status" className="mb-4 text-sm">
          Trwa analiza nowych wydatków. Wyniki pojawią się tutaj po zakończeniu.
        </p>
      ) : null}
      {activity.isError ? (
        <p role="alert" className="mb-4 text-sm">
          Nie udało się pobrać stanu analiz.
        </p>
      ) : null}
      {activity.data?.recent_outcomes.some((j) => j.state === "uncertain") ? (
        <p className="card mb-4 text-sm">
          Wynik analizy jest nieznany. Nie wysyłamy jej ponownie; przypisz
          kategorię ręcznie. Zużycie może pozostać nieznane.
        </p>
      ) : null}
      {activity.data?.recent_outcomes.some(
        (j) => j.reason_code === "quota_exceeded",
      ) ? (
        <p className="mb-4 text-sm">
          Osiągnięto limit analiz. Te wydatki nie zostaną wysłane kolejnego
          dnia; przypisz kategorię ręcznie.
        </p>
      ) : null}
      {activity.data?.recent_outcomes.some(
        (j) =>
          j.result_kind === "no_suggestion" ||
          j.state === "failed" ||
          (j.state === "cancelled" && j.reason_code !== "quota_exceeded"),
      ) ? (
        <p className="mb-4 text-sm">
          Niektóre analizy zakończyły się bez propozycji. Opis, katalog lub
          źródło mogły przekroczyć dozwolony zakres — sprawdź kategorię ręcznie.
        </p>
      ) : null}
      <ProposalReview
        items={proposals.data?.items ?? []}
        maxItems={proposals.data?.page_size ?? 20}
        onNextPage={
          proposals.data?.next_cursor
            ? () => setCursor(proposals.data.next_cursor)
            : undefined
        }
        onFirstPage={cursor ? () => setCursor(null) : undefined}
      />
    </div>
  );
}
