import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { TransactionEditorDialog } from "./TransactionEditorDialog";

let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);

beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "owner@example.test",
      display_name: "Owner",
      is_active: true,
    },
  });
});

it("keeps protected ledger values read-only and opens reviewed split editing only after closing itself", async () => {
  vi.spyOn(api, "get").mockResolvedValue({
    data: {
      ledger_editable: false,
      ledger_lock_reason: "Zaimportowana transakcja jest chroniona.",
      transaction: {
        id: "tx",
        transaction_date: "2026-11-24",
        description: "Market",
        type: "expense",
        is_pending: false,
        project_id: null,
        source: "import",
        updated_at: "2026-11-24T12:00:00Z",
        postings: [
          {
            id: "a",
            transaction_id: "tx",
            account_id: "account",
            category_id: null,
            source_amount: 10000,
            source_currency: "PLN",
            base_amount_pln: 10000,
            fx_rate: 1,
            is_budget_impact: true,
            direction: "debit",
          },
          {
            id: "b",
            transaction_id: "tx",
            account_id: null,
            category_id: "food",
            source_amount: 6000,
            source_currency: "PLN",
            base_amount_pln: 6000,
            fx_rate: 1,
            is_budget_impact: true,
            direction: "credit",
          },
          {
            id: "c",
            transaction_id: "tx",
            account_id: null,
            category_id: "house",
            source_amount: 4000,
            source_currency: "PLN",
            base_amount_pln: 4000,
            fx_rate: 1,
            is_budget_impact: true,
            direction: "credit",
          },
        ],
      },
    },
  });
  const close = vi.fn();
  render(<TransactionEditorDialog id="tx" onClose={close} />, { wrapper });

  expect(
    await screen.findByText("Zaimportowana transakcja jest chroniona."),
  ).toBeVisible();
  expect(screen.getByLabelText("Opis księgowy")).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "Edytuj podział kategorii" }),
  );
  expect(
    screen.getByRole("dialog", { name: "Kategorie wydatku" }),
  ).toBeVisible();
  expect(close).not.toHaveBeenCalled();
});

it("offers the reviewed categorization workflow for a protected single-category expense", async () => {
  vi.spyOn(api, "get").mockResolvedValue({
    data: {
      ledger_editable: false,
      ledger_lock_reason: "Płatność pożyczki jest powiązana z harmonogramem.",
      transaction: {
        id: "loan",
        transaction_date: "2026-11-24",
        description: "Rata",
        type: "expense",
        is_pending: false,
        project_id: null,
        source: "import",
        updated_at: "2026-11-24T12:00:00Z",
        postings: [
          {
            id: "a",
            transaction_id: "loan",
            account_id: "account",
            category_id: null,
            source_amount: 10000,
            source_currency: "PLN",
            base_amount_pln: 10000,
            fx_rate: 1,
            is_budget_impact: true,
            direction: "debit",
          },
          {
            id: "b",
            transaction_id: "loan",
            account_id: null,
            category_id: "loan",
            source_amount: 10000,
            source_currency: "PLN",
            base_amount_pln: 10000,
            fx_rate: 1,
            is_budget_impact: true,
            direction: "credit",
          },
        ],
      },
    },
  });
  render(<TransactionEditorDialog id="loan" onClose={vi.fn()} />, { wrapper });

  await screen.findByText("Płatność pożyczki jest powiązana z harmonogramem.");
  expect(
    screen.getByRole("button", { name: "Edytuj podział kategorii" }),
  ).toBeVisible();
  expect(
    screen.queryByText("Ten zapis ma kilka kategorii."),
  ).not.toBeInTheDocument();
});

it("retains the annotation tag and project controls in the atomic editor", async () => {
  vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).includes("/work/projects")
      ? [{ id: "project", name: "Remont", status: "completed" }]
      : String(url).endsWith("/tags")
        ? [{ id: "tag", name: "Wakacje" }]
        : {
            ledger_editable: false,
            ledger_lock_reason: "Chroniona.",
            transaction: {
              id: "annotation",
              transaction_date: "2026-11-24",
              description: "Bank",
              type: "income",
              is_pending: false,
              project_id: null,
              source: "import",
              updated_at: "2026-11-24T12:00:00Z",
              postings: [],
              annotations: {
                display_description: null,
                original_description: "Bank",
                note: null,
                tags: [],
                project_id: null,
                project_name: null,
                version: 0,
                context_snapshot: "a".repeat(64),
                limits: {
                  display_description: 200,
                  note: 5000,
                  tag_name: 60,
                  tags: 20,
                },
              },
            },
          },
  }));
  render(<TransactionEditorDialog id="annotation" onClose={vi.fn()} />, {
    wrapper,
  });

  await screen.findByLabelText("Własny opis");
  expect(screen.getByLabelText("Notatka")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Nowy tag"), {
    target: { value: "Dom" },
  });
  expect(screen.getByRole("button", { name: "Dodaj tag" })).toBeVisible();
  expect(
    await screen.findByRole("button", { name: "Dodaj tag Wakacje" }),
  ).toBeVisible();
  expect(screen.getByLabelText("Projekt")).toBeVisible();
});
