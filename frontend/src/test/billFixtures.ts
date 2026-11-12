import type { BillResponse } from "../api/bills";

export function syntheticBill(
  overrides: Partial<BillResponse> = {},
): BillResponse {
  return {
    id: "bill-1",
    kind: "invoice",
    supplier_name: "Dostawca",
    supplier_tax_id: null,
    number: "FV/1",
    issue_date: "2026-10-01",
    sale_date: null,
    due_date: "2026-10-15",
    payee_iban: null,
    description: "Usługa",
    category_id: null,
    payment_account_id: null,
    total_minor: 10000,
    currency: "PLN",
    declaration: "payable",
    lifecycle: "active",
    review: "approved",
    version: 2,
    paid_minor: 0,
    remaining_minor: 10000,
    reconciliation: "none",
    sources: [],
    allocations: [],
    extraction_revision_id: null,
    coverage: null,
    recurring_decision: null,
    forecast_exclusion_reasons: [],
    ...overrides,
  };
}
