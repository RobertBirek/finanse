import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { categorySelectFixture } from "../../../test/categoryFixtures";
import { rowFixture } from "../../../test/bankImportFixtures";
import { ImportGroupEditor } from "./ImportGroupEditor";

it("uses sorted full paths for both operation and fee, keeping the existing type/active filters and IDs", () => {
  const onSave = vi.fn();
  const row = rowFixture();
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ImportGroupEditor
        batchId="batch-a"
        rows={[{ ...row, bank_fields: { ...row.bank_fields!, fee: 100 } }]}
        accounts={[
          {
            id: "account-pln",
            name: "Konto",
            type: "checking",
            currency: "PLN",
            is_active: true,
            is_budget_account: true,
            balance_pln: 10000,
            opened_at: "2026-01-01",
            closed_at: null,
          },
        ]}
        categories={categorySelectFixture}
        sources={[]}
        pending={false}
        onSave={onSave}
      />
    </QueryClientProvider>,
  );
  const category = screen.getByLabelText("Kategoria");
  const fee = screen.getByLabelText("Kategoria opłaty / zwrotu opłaty");
  for (const select of [category, fee]) {
    expect(
      within(select)
        .getAllByRole("option")
        .slice(1)
        .map((option) => option.textContent),
    ).toEqual(["Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
  }
  fireEvent.change(screen.getByLabelText("Rodzaj operacji"), {
    target: { value: "income" },
  });
  expect(
    within(category)
      .getAllByRole("option")
      .slice(1)
      .map((option) => option.textContent),
  ).toEqual(["Pensja"]);
  fireEvent.change(screen.getByLabelText("Rodzaj operacji"), {
    target: { value: "expense" },
  });
  fireEvent.change(category, { target: { value: "gas" } });
  fireEvent.change(fee, { target: { value: "water" } });
  fireEvent.submit(screen.getByRole("form"));
  expect(onSave).toHaveBeenCalledWith(
    expect.objectContaining({ category_id: "gas", fee_category_id: "water" }),
  );
});
