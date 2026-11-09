import type { CommitResult } from "../../../api/bankImports";

export function ImportReceipt({ receipt }: { receipt: CommitResult }) {
  return (
    <section
      className="card space-y-2"
      aria-label="Wynik importu"
      role="status"
    >
      <h2 className="text-xl">Zapisano wynik importu</h2>
      <p>
        Nowe transakcje: {receipt.transaction_ids.length} · Powiązane wiersze:{" "}
        {receipt.linked_row_ids.length}
      </p>
      <p>
        {receipt.commit_state === "committed"
          ? "Wybrane operacje rozliczono."
          : "Import częściowy. Pozostałe wiersze nadal wymagają decyzji."}
      </p>
      <p className="break-all text-xs">Potwierdzenie: {receipt.receipt_id}</p>
    </section>
  );
}
