import { render, screen } from "@testing-library/react";
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
    render(<FinanceTransactions />);
    expect(
      screen.getByRole("heading", { name: "Transakcje" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Historia z filtrami")).toBeInTheDocument();
    expect(screen.getByText("Dodaj transakcję")).toBeInTheDocument();
    expect(screen.getByText("Formularz transakcji")).toBeInTheDocument();
  });
});
