import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BillResponse } from "../api/bills";
import api from "../lib/api";
import { FinanceDocuments } from "./FinanceDocuments";

const bill: BillResponse = {
  id: "bill-1",
  kind: "invoice",
  supplier_name: "Dostawca",
  supplier_tax_id: null,
  number: "FV/1",
  issue_date: "2026-10-01",
  sale_date: null,
  due_date: null,
  payee_iban: null,
  description: "Usługa",
  category_id: null,
  payment_account_id: null,
  total_minor: 10000,
  currency: "EUR",
  declaration: "declared_paid",
  lifecycle: "active",
  review: "approved",
  version: 1,
  paid_minor: 4000,
  remaining_minor: 6000,
  reconciliation: "partial",
  sources: [],
  allocations: [],
  extraction_revision_id: null,
  coverage: null,
  recurring_decision: null,
  forecast_exclusion_reasons: [],
};

afterEach(() => vi.restoreAllMocks());

function renderRegister(items = [bill]) {
  vi.spyOn(api, "get").mockResolvedValue({
    data: { items, total: items.length, limit: 25, offset: 0 },
  } as never);
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/finances/documents"]}>
        <FinanceDocuments />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FinanceDocuments register", () => {
  it("separates declared paid from partial reconciliation and renders the remaining currency amount", async () => {
    renderRegister();
    expect(
      await screen.findByText(/Deklarowano opłacenie/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Uzgodnienie: partial/)).toBeInTheDocument();
    expect(
      screen.getByText((_, node) => node?.textContent === "60,00 €"),
    ).toBeInTheDocument();
  });

  it("does not label an unknown-currency total as PLN", async () => {
    renderRegister([{ ...bill, id: "unknown", currency: null }]);
    expect((await screen.findAllByText("—")).length).toBe(2);
    expect(screen.queryByText("100,00 zł")).not.toBeInTheDocument();
  });
});
