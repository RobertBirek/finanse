import type { BillResponse } from "../../../api/bills";

export function billPaymentPresentation(
  bill: Pick<
    BillResponse,
    "declaration" | "remaining_minor" | "reconciliation"
  >,
) {
  const declared = bill.declaration === "declared_paid";
  const statusLabel =
    bill.reconciliation === "full"
      ? "Rozliczona z księgą"
      : declared
        ? bill.reconciliation === "partial"
          ? "Opłacona deklaracyjnie — częściowo powiązana z księgą"
          : "Opłacona deklaracyjnie — bez powiązania z księgą"
        : bill.declaration === "payable"
          ? "Do zapłaty"
          : "Brak deklaracji opłacenia";
  return {
    payableMinor: declared ? 0 : bill.remaining_minor,
    unlinkedMinor: bill.remaining_minor,
    statusLabel,
    declared,
  };
}
