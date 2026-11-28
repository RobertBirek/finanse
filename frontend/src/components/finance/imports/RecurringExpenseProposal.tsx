import { useEffect, useState } from "react";
import type { Account, Category } from "../../../api/finance";
import { ScheduledItemForm } from "../ScheduledItemForm";
import { useRecurringExpenseProposal } from "../../../api/bankImports";
import { sourceMoney } from "./importPresentation";

export function RecurringExpenseProposal({
  batchId,
  rowId,
  accountId,
  accounts,
  categories,
}: {
  batchId: string;
  rowId: string;
  accountId: string;
  accounts: Account[];
  categories: Category[];
}) {
  const proposal = useRecurringExpenseProposal();
  const [requestedFor, setRequestedFor] = useState<string | null>(null);
  const [showDraft, setShowDraft] = useState(false);
  const requestKey = `${batchId}:${rowId}:${accountId}`;

  useEffect(() => {
    setRequestedFor(null);
    setShowDraft(false);
  }, [requestKey]);

  const result = requestedFor === requestKey ? proposal.data : undefined;
  return (
    <section
      className="space-y-3 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"
      aria-label="Sugestia pozycji cyklicznej"
    >
      <h3 className="font-medium">Sugestia pozycji cyklicznej</h3>
      <p className="text-gray-500 dark:text-gray-400">
        Odczyt nie zapisuje harmonogramu ani transakcji. Sugestia wymaga
        osobnego sprawdzenia i zapisu formularza.
      </p>
      {!requestedFor ? (
        <button
          className="btn-secondary"
          type="button"
          disabled={proposal.isPending}
          onClick={() => {
            setShowDraft(false);
            setRequestedFor(requestKey);
            proposal.mutate({ batchId, rowId, accountId });
          }}
        >
          Sprawdź sugestię cykliczności
        </button>
      ) : null}
      {proposal.isPending && requestedFor === requestKey ? (
        <p role="status">Sprawdzanie potwierdzonych obserwacji…</p>
      ) : null}
      {proposal.error && requestedFor === requestKey ? (
        <>
          <p role="alert">
            Nie udało się odczytać sugestii. Możesz ponowić sprawdzenie.
          </p>
          <button
            className="btn-secondary"
            type="button"
            disabled={proposal.isPending}
            onClick={() => proposal.mutate({ batchId, rowId, accountId })}
          >
            Ponów sprawdzenie sugestii
          </button>
        </>
      ) : null}
      {result ? (
        <>
          {result.status === "proposed" && result.proposal ? (
            <>
              <p>
                Możliwy nowy harmonogram:{" "}
                <strong>{result.proposal.merchant}</strong>
                {" · "}
                {result.proposal.frequency === "monthly"
                  ? "co miesiąc"
                  : "co rok"}
                {" · "}
                {result.proposal.amount_kind === "stable" &&
                result.proposal.amount_minor !== null
                  ? sourceMoney(
                      Math.abs(result.proposal.amount_minor),
                      result.proposal.currency,
                    )
                  : "zmienna kwota"}
              </p>
              <p className="text-gray-500 dark:text-gray-400">
                Nie wyznaczono terminu na podstawie dat bankowych. Ustaw go
                ręcznie w formularzu.
              </p>
              <EvidenceList evidence={result.evidence} />
              {result.proposal.currency !== "PLN" ? (
                <p role="alert">
                  Harmonogramy obsługują obecnie tylko PLN; ta sugestia nie
                  wypełnia formularza.
                </p>
              ) : !showDraft ? (
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={() => setShowDraft(true)}
                >
                  Przygotuj edytowalny formularz harmonogramu
                </button>
              ) : (
                <ScheduledItemForm
                  mode="create"
                  accounts={accounts}
                  categories={categories}
                  initialDraft={{
                    name: result.proposal.merchant,
                    account_id: accountId,
                    cadence: result.proposal.frequency,
                    due_day: "",
                    amount_method:
                      result.proposal.amount_kind === "stable"
                        ? "fixed"
                        : "last_actual",
                    fixed_amount_pln:
                      result.proposal.amount_kind === "stable" &&
                      result.proposal.amount_minor !== null
                        ? Math.abs(result.proposal.amount_minor)
                        : null,
                  }}
                  onCancel={() => setShowDraft(false)}
                  onSuccess={() => setShowDraft(false)}
                />
              )}
            </>
          ) : (
            <>
              <p>
                Brak bezpiecznej sugestii do utworzenia nowego harmonogramu.
              </p>
              {result.reason ? (
                <p className="text-gray-500 dark:text-gray-400">
                  Powód: {result.reason}
                </p>
              ) : null}
              <EvidenceList evidence={result.evidence} />
            </>
          )}
        </>
      ) : null}
    </section>
  );
}

function EvidenceList({
  evidence,
}: {
  evidence: Array<{
    strong_identity: string;
    occurred_on: string;
    amount_minor: number;
    currency: string;
  }>;
}) {
  if (evidence.length === 0) return null;
  return (
    <section aria-label="Dowody sugestii">
      <h4 className="font-medium">{evidence.length} potwierdzone obserwacje</h4>
      <ul className="mt-1 list-inside list-disc text-gray-500 dark:text-gray-400">
        {evidence.map((item) => (
          <li key={item.strong_identity}>
            {item.occurred_on} ·{" "}
            {sourceMoney(Math.abs(item.amount_minor), item.currency)}
          </li>
        ))}
      </ul>
    </section>
  );
}
