import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import api from "../../../lib/api";
import {
  useSerializedIntentKey,
  useBill,
  useBillCoverage,
  type BillResponse,
  type CoverageCandidate,
} from "../../../api/bills";
import { Dialog } from "../../Dialog";
const pln = (value: number | null | undefined) =>
  value == null
    ? "niedostępna"
    : new Intl.NumberFormat("pl-PL", {
        style: "currency",
        currency: "PLN",
      }).format(value / 100);
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
  const currentBill = useBill(bill.id, false);
  const keyFor = useSerializedIntentKey();
  const [selected, setSelected] = useState<CoverageCandidate | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [comparison, setComparison] = useState<BillResponse | null>(null);
  const [needsNewDecision, setNeedsNewDecision] = useState(false);
  const activeBill = comparison ?? bill;
  const coveredEstimate = candidates.data?.find(
    (candidate) =>
      candidate.scheduled_item_id === bill.coverage?.scheduled_item_id &&
      candidate.occurrence_date === bill.coverage?.occurrence_date,
  )?.estimate_amount_pln;
  const decide = (choice: "replace" | "separate") =>
    coverage.decide.mutate(
      {
        billId: activeBill.id,
        version: activeBill.version,
        choice,
        ...(choice === "replace" && selected
          ? {
              scheduled_item_id: selected.scheduled_item_id,
              occurrence_date: selected.occurrence_date,
            }
          : {}),
        idempotencyKey: keyFor({
          action: "coverage",
          billId: activeBill.id,
          version: activeBill.version,
          choice,
          scheduled_item_id: selected?.scheduled_item_id,
          occurrence_date: selected?.occurrence_date,
        }),
      },
      {
        onSuccess: onClose,
        onError: (error) => {
          if (
            (error as { response?: { status?: number } }).response?.status ===
            409
          ) {
            setComparison(null);
            setNeedsNewDecision(true);
          }
        },
      },
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
            Faktura: {pln(bill.total_minor)}, pozostało:{" "}
            {pln(bill.remaining_minor)}. Odpięcie przywróci estymatę{" "}
            {pln(coveredEstimate)} dla tego terminu.
          </p>
          {confirmUnlink ? (
            <div className="mt-4 rounded border border-amber-700 p-3 text-sm text-amber-100">
              Potwierdź: estymata dla {bill.coverage.occurrence_date} (
              {pln(coveredEstimate)}) zostanie przywrócona do prognozy.
              <div className="mt-2 flex gap-2">
                <button
                  className="btn-primary"
                  type="button"
                  disabled={needsNewDecision}
                  onClick={() =>
                    coverage.unlink.mutate(
                      {
                        billId: activeBill.id,
                        expected_version: activeBill.version,
                        idempotencyKey: keyFor({
                          action: "unlink-coverage",
                          billId: activeBill.id,
                          version: activeBill.version,
                        }),
                      },
                      {
                        onSuccess: onClose,
                        onError: (error) => {
                          if (
                            (error as { response?: { status?: number } })
                              .response?.status === 409
                          ) {
                            setComparison(null);
                            setNeedsNewDecision(true);
                          }
                        },
                      },
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
              disabled={!selected || needsNewDecision}
              onClick={() => decide("replace")}
            >
              Zastąp estymatę
            </button>
            <button
              className="btn-secondary"
              type="button"
              disabled={needsNewDecision}
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
      {needsNewDecision ? (
        <div className="mt-3 rounded border border-amber-700 p-3 text-sm text-amber-100">
          Wersja przed zmianą: {bill.version}. Zapis jest zablokowany do
          odświeżenia.
          {comparison ? <p>Aktualna wersja: {comparison.version}.</p> : null}
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={async () => {
                const result = await currentBill.refetch();
                if (result.data) setComparison(result.data);
              }}
            >
              Odśwież aktualny dokument
            </button>
            {comparison ? (
              <button
                type="button"
                className="btn-primary"
                onClick={() => setNeedsNewDecision(false)}
              >
                Rozumiem — podejmuję nową decyzję
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
