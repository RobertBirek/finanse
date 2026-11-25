import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import api from "../../lib/api";
import { parseStatementBalance } from "../../lib/statementBalance";
import { BalanceReconciliation } from "./BalanceReconciliation";

it("converts signed statement amounts without floating-point rounding", () => {
  expect(parseStatementBalance("-90071992547409,93")).toBe("-9007199254740993");
  expect(parseStatementBalance("0")).toBe("0");
  expect(parseStatementBalance("1,999")).toBeNull();
  expect(parseStatementBalance("92233720368547758,08")).toBeNull();
});

it("shows the difference in account currency and links the booked history", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValue({
    data: [{ id: "checking", name: "Rachunek", currency: "EUR" }],
  });
  const post = vi.spyOn(api, "post").mockResolvedValue({
    data: {
      day: "2026-11-23",
      currency: "EUR",
      ledger_minor: "1230",
      statement_minor: "1200",
      difference_minor: "-30",
    },
  });
  try {
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <BalanceReconciliation onHistory={() => undefined} />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    await screen.findByRole("option", { name: "Rachunek (EUR)" });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "checking" },
    });
    fireEvent.change(screen.getByLabelText("Data końcowa wyciągu"), {
      target: { value: "2026-11-23" },
    });
    fireEvent.change(screen.getByLabelText("Saldo końcowe z wyciągu (EUR)"), {
      target: { value: "12,00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Porównaj salda" }));
    expect(await screen.findByRole("status")).toHaveTextContent("−0,30 EUR");
    expect(
      screen.getByRole("link", { name: "Przejdź do historii konta" }),
    ).toHaveAttribute(
      "href",
      "/finances/transactions?account_id=checking&date_to=2026-11-23&date_basis=booking",
    );
    expect(post).toHaveBeenCalledWith(
      "/finance/accounts/checking/balance-reconciliation",
      {
        day: "2026-11-23",
        statement_minor: "1200",
      },
    );
  } finally {
    get.mockRestore();
    post.mockRestore();
  }
});
