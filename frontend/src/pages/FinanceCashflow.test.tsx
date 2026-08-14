import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FinanceCashflow } from "./FinanceCashflow";

const { useCashflowForecast } = vi.hoisted(() => ({
  useCashflowForecast: vi.fn(),
}));

vi.mock("../api/finance", () => ({ useCashflowForecast }));

describe("FinanceCashflow", () => {
  it("shows the existing read-only cashflow forecast", () => {
    useCashflowForecast.mockReturnValue({
      data: {
        next_payday: "2026-06-10",
        projected_balance_before_next_payday_pln: 250000,
        lowest_balance_pln: 100000,
        safe_daily_limit_pln: 25000,
      },
      isLoading: false,
      isError: false,
    });

    render(<FinanceCashflow />);

    expect(
      screen.getByRole("heading", { name: "Płynność" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Przed wypłatą")).toBeInTheDocument();
    expect(screen.getByText(/2.*500,00 PLN/)).toBeInTheDocument();
  });
});
