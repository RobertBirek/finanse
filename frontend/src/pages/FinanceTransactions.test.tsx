import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FinanceTransactions } from "./FinanceTransactions";

const { useAccounts } = vi.hoisted(() => ({ useAccounts: vi.fn() }));

vi.mock("../api/finance", () => ({ useAccounts }));

vi.mock("../components/finance/AccountTransactions", () => ({
  AccountTransactions: () => <p>Lista kont</p>,
}));

vi.mock("../components/finance/TransactionForm", () => ({
  TransactionForm: () => <p>Formularz transakcji</p>,
}));

describe("FinanceTransactions", () => {
  it("loads accounts and presents the transaction page", () => {
    useAccounts.mockReturnValue({ data: [], isLoading: false, isError: false });

    render(<FinanceTransactions />);

    expect(
      screen.getByRole("heading", { name: "Transakcje" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Dodaj transakcję" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Formularz transakcji")).toBeInTheDocument();
    expect(screen.getByText("Lista kont")).toBeInTheDocument();
    expect(useAccounts).toHaveBeenCalledOnce();
  });
});
