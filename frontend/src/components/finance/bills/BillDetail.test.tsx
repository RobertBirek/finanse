import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BillDetail } from "./BillDetail";

vi.mock("../../../api/documents", () => ({
  useDocumentPreview: () => ({ data: undefined, isError: false }),
  useDocumentOriginal: () => ({ data: undefined, isError: false }),
}));

const bill = {
  id: "bill-1",
  kind: "invoice" as const,
  supplier_name: "Dostawca",
  supplier_tax_id: null,
  number: "FV/1",
  issue_date: "2026-10-01",
  sale_date: null,
  due_date: "2026-10-15",
  payee_iban: null,
  description: "Usługa",
  category_id: "category-1",
  payment_account_id: "account-1",
  total_minor: 10000,
  currency: "PLN" as const,
  declaration: "declared_paid" as const,
  lifecycle: "active" as const,
  review: "approved" as const,
  version: 7,
  paid_minor: 4000,
  remaining_minor: 6000,
  reconciliation: "partial" as const,
  sources: [],
  allocations: [
    { id: "allocation-1", posting_id: "posting-1", amount_minor: 4000 },
  ],
  extraction_revision_id: null,
  coverage: null,
  recurring_decision: null,
  forecast_exclusion_reasons: [],
};

describe("BillDetail", () => {
  it("keeps a declared payment distinct from partial reconciliation and offers audited lifecycle and unlink actions", () => {
    const onLifecycle = vi.fn();
    const onUnlink = vi.fn();
    render(
      <BillDetail
        bill={bill}
        onClose={vi.fn()}
        onPayment={vi.fn()}
        onCoverage={vi.fn()}
        onLifecycle={onLifecycle}
        onUnlink={onUnlink}
      />,
    );

    expect(screen.getByText("declared_paid")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Archiwizuj" }));
    expect(onLifecycle).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź zmianę stanu" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Odłącz alokację" }));
    expect(onUnlink).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Potwierdź odłączenie" }),
    );
    expect(onLifecycle).toHaveBeenCalledWith("archived");
    expect(onUnlink).toHaveBeenCalledWith("allocation-1");
  });
});
