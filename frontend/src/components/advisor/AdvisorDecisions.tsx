import { Link } from "react-router-dom";
import { CashflowScenario } from "./CashflowScenario";
import { SpendingComparison } from "./SpendingComparison";
import {
  useAttention,
  useAttentionExplanation,
} from "../../api/advisorDecisions";

const sourceLabels = {
  payment: "Otwórz prognozę płatności",
  document: "Otwórz dokumenty do przeglądu",
  task: "Otwórz zadania",
};

export function AdvisorDecisions() {
  const facts = useAttention();
  const explanation = useAttentionExplanation();
  const busy = facts.isPending || explanation.isPending;

  return (
    <section
      aria-label="Wsparcie decyzji"
      className="space-y-3 rounded-lg border border-gray-800 p-3"
    >
      <button
        type="button"
        className="btn-secondary"
        disabled={busy}
        onClick={() => {
          explanation.reset();
          facts.mutate();
        }}
      >
        Co wymaga mojej uwagi?
      </button>
      {facts.isPending && <p role="status">Sprawdzam priorytety…</p>}
      {facts.isError && <p role="alert">Nie udało się pobrać priorytetów.</p>}
      {facts.data && (
        <>
          <p className="text-sm text-gray-400">Stan na {facts.data.as_of}</p>
          {facts.data.items.length === 0 ? (
            <p>Nie ma spraw wymagających uwagi.</p>
          ) : (
            <>
              <ol className="space-y-2">
                {facts.data.items.map((item) => (
                  <li
                    key={`${item.kind}:${item.source_id}`}
                    className="break-words text-sm"
                  >
                    <p className="font-semibold">{item.title}</p>
                    <p>
                      {item.reason}{" "}
                      {item.due_date && (
                        <time dateTime={item.due_date}>{item.due_date}</time>
                      )}
                    </p>
                    <Link className="underline" to={item.href}>
                      {sourceLabels[item.kind]}
                    </Link>
                  </li>
                ))}
              </ol>
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                onClick={() => explanation.mutate()}
              >
                Objaśnij priorytety z OpenAI
              </button>
            </>
          )}
        </>
      )}
      {explanation.isPending && <p role="status">Pobieram objaśnienie…</p>}
      {(explanation.isError || explanation.data?.status === "unavailable") && (
        <p role="alert">Objaśnienie jest niedostępne.</p>
      )}
      {explanation.data?.status === "no_facts" && (
        <p>Nie ma już spraw do objaśnienia.</p>
      )}
      {explanation.data?.status === "ok" && (
        <p className="whitespace-pre-wrap break-words">
          Komentarz OpenAI: {explanation.data.text}
        </p>
      )}
      <CashflowScenario />
      <SpendingComparison />
    </section>
  );
}
