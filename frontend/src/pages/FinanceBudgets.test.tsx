import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FinanceBudgets } from "./FinanceBudgets";

const { useCategorySummary } = vi.hoisted(() => ({
  useCategorySummary: vi.fn(),
}));

vi.mock("../api/finance", () => ({ useCategorySummary }));

vi.mock("../components/finance/CategorySpendTree", () => ({
  CategorySpendTree: ({ title }: { title: string }) => <h2>{title}</h2>,
}));

describe("FinanceBudgets", () => {
  it("loads the category summary for the current month", () => {
    useCategorySummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    });

    render(<FinanceBudgets />);

    expect(screen.getByRole("heading", { name: "Budżet" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Wydatki według kategorii" }),
    ).toBeInTheDocument();
    expect(useCategorySummary).toHaveBeenCalledWith({
      month: new Date().getMonth() + 1,
      year: new Date().getFullYear(),
    });
  });
});
