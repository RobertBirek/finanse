import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import api from "../../../lib/api";
import {
  stableKey,
  useBillCoverage,
  type BillResponse,
  type CoverageCandidate,
} from "../../../api/bills";
import { Dialog } from "../../Dialog";
export function BillCoverageDialog({
  bill,
  onClose,
}: {
  bill: BillResponse;
  onClose: () => void;
}) {
  const candidates = useQuery({
    queryKey: ["finance", "bills", bill.id, "coverage-candidates"],
    queryFn: async () =>
      (
        await api.get<CoverageCandidate[]>(
          `/finance/bills/${bill.id}/coverage-candidates`,
        )
      ).data,
  });
  const coverage = useBillCoverage();
  const [selected, setSelected] = useState<CoverageCandidate | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const decide = (choice: "replace" | "separate") =>
    coverage.decide.mutate(
      {
        billId: bill.id,
        version: bill.version,
        choice,
        ...(choice === "replace" && selected
          ? {
              scheduled_item_id: selected.scheduled_item_id,
              occurrence_date: selected.occurrence_date,
            }
          : {}),
        idempotencyKey: stableKey(),
      },
      { onSuccess: onClose },
    );
  return (
    <Dialog
      label="Wpływ na prognozę"
      onClose={onClose}
      busy={coverage.decide.isPending || coverage.unlink.isPending}
    >
      <h2 className="text-lg font-semibold text-white">Wpływ na prognozę</h2>
      {bill.coverage ? (
        <>
          <p className="mt-3 text-sm text-gray-300">
            Faktura zastępuje wystąpienie {bill.coverage.occurrence_date}.
            Odpięcie przywróci estymatę cykliczną.
          </p>
          {confirmUnlink ? (
            <div className="mt-4 rounded border border-amber-700 p-3 text-sm text-amber-100">
              Potwierdź: estymata cykliczna zostanie przywrócona do prognozy.
              <div className="mt-2 flex gap-2">
                <button
                  className="btn-primary"
                  type="button"
                  onClick={() =>
                    coverage.unlink.mutate(
                      {
                        billId: bill.id,
                        expected_version: bill.version,
                        idempotencyKey: stableKey(),
                      },
                      { onSuccess: onClose },
                    )
                  }
                >
                  Potwierdź odłączenie
                </button>
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={() => setConfirmUnlink(false)}
                >
                  Wróć
                </button>
              </div>
            </div>
          ) : (
            <button
              className="btn-secondary mt-4"
              type="button"
              onClick={() => setConfirmUnlink(true)}
            >
              Odłącz i przywróć estymatę
            </button>
          )}
        </>
      ) : (
        <>
          <p className="mt-2 text-sm text-gray-400">
            Wybierz konkretne wystąpienie. Zastąpienie usuwa jedną estymatę;
            osobno pozostawia obie pozycje.
          </p>
          <div className="mt-4 space-y-2">
            {candidates.data?.map((candidate) => (
              <label
                key={`${candidate.scheduled_item_id}:${candidate.occurrence_date}`}
                className="block text-sm text-gray-300"
              >
                <input
                  type="radio"
                  name="coverage"
                  onChange={() => setSelected(candidate)}
                />{" "}
                {candidate.name} · {candidate.occurrence_date} · estymata{" "}
                {candidate.estimate_amount_pln == null
                  ? "niedostępna"
                  : `${(candidate.estimate_amount_pln / 100).toFixed(2)} PLN`}
              </label>
            ))}
          </div>
          <div className="mt-5 flex gap-2">
            <button
              className="btn-primary"
              type="button"
              disabled={!selected}
              onClick={() => decide("replace")}
            >
              Zastąp estymatę
            </button>
            <button
              className="btn-secondary"
              type="button"
              onClick={() => decide("separate")}
            >
              Pokaż osobno
            </button>
          </div>
        </>
      )}
      {coverage.decide.error || coverage.unlink.error ? (
        <p role="alert" className="mt-3 text-sm text-red-300">
          Nie udało się zmienić prognozy. Odśwież dokument i sprawdź aktualny
          stan.
        </p>
      ) : null}
    </Dialog>
  );
}
