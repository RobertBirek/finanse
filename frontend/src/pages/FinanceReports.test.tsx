import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FinanceReports } from "./FinanceReports";

const { useCategorySummary, useFinancialSummary } = vi.hoisted(() => ({
  useCategorySummary: vi.fn(),
  useFinancialSummary: vi.fn(),
}));

vi.mock("../api/finance", () => ({
  useCategorySummary,
  useFinancialSummary,
}));

vi.mock("../components/finance/CategorySpendTree", () => ({
  CategorySpendTree: ({ title }: { title: string }) => <h2>{title}</h2>,
}));

describe("FinanceReports", () => {
  it("shows monthly financial totals and passes one period to both summaries", () => {
    useFinancialSummary.mockReturnValue({
      data: {
        income_total_pln: 500000,
        expense_total_pln: 123456,
        net_total_pln: 376544,
      },
      isLoading: false,
      isError: false,
    });
    useCategorySummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });

    render(<FinanceReports />);

    expect(
      screen.getByRole("heading", { name: "Raporty" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Przychody")).toBeInTheDocument();
    expect(screen.getByText("Wydatki")).toBeInTheDocument();
    expect(screen.getByText("Bilans")).toBeInTheDocument();
    expect(screen.getByText(/5.*000,00 PLN/)).toBeInTheDocument();
    expect(useFinancialSummary).toHaveBeenCalledWith({
      month: new Date().getMonth() + 1,
      year: new Date().getFullYear(),
    });
    expect(useCategorySummary).toHaveBeenCalledWith({
      month: new Date().getMonth() + 1,
      year: new Date().getFullYear(),
    });
  });
});
