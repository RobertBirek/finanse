import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { FinanceTransactions } from "./FinanceTransactions";

vi.mock("../components/finance/TransactionSearch", () => ({
  TransactionSearch: () => <p>Historia z filtrami</p>,
}));
vi.mock("../components/finance/TransactionForm", () => ({
  TransactionForm: () => <p>Formularz transakcji</p>,
}));

describe("FinanceTransactions", () => {
  it("prioritizes searchable history while keeping transaction creation available", () => {
    render(
      <MemoryRouter>
        <FinanceTransactions />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Transakcje" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Historia z filtrami")).toBeInTheDocument();
    expect(screen.queryByText("Formularz transakcji")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Dodaj transakcję/ }));
    expect(screen.getByText("Formularz transakcji")).toBeInTheDocument();
  });
});
