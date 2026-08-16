import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CashflowForecast as CashflowForecastData } from "../../api/finance";
import { CashflowForecast } from "./CashflowForecast";

function makeForecast(
  overrides: Partial<CashflowForecastData> = {},
): CashflowForecastData {
  return {
    last_payday: "2026-07-10",
    next_payday: "2026-08-10",
    opening_balance_pln: 100000,
    projected_balance_before_next_payday_pln: 50000,
    safe_daily_limit_pln: 17000,
    lowest_balance_pln: 42000,
    days: [{ date: "2026-08-01", projected_balance_pln: 46000 }],
    suggestions: [],
    budgets: {
      total_budget_pln: 80000,
      total_spent_pln: 48000,
      remaining_pln: 32000,
    },
    ...overrides,
  };
}

describe("CashflowForecast — budżety", () => {
  it("pokazuje limit, wydano i pozostało budżetu oraz pasek postępu", () => {
    render(
      <CashflowForecast
        forecast={makeForecast()}
        loading={false}
        error={false}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Budżety w tym miesiącu" }),
    ).toBeInTheDocument();
    expect(screen.getByText("800,00 PLN")).toBeInTheDocument();
    expect(screen.getByText("480,00 PLN")).toBeInTheDocument();
    expect(screen.getByText("320,00 PLN")).toBeInTheDocument();

    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "60");
  });

  it("pokazuje ostrzeżenie gdy pozostało budżetu przekracza prognozowaną płynność", () => {
    render(
      <CashflowForecast
        forecast={makeForecast({
          projected_balance_before_next_payday_pln: 20000,
        })}
        loading={false}
        error={false}
      />,
    );

    expect(
      screen.getByText(
        /Budżety przekraczają prognozowaną płynność o 120,00 PLN/,
      ),
    ).toBeInTheDocument();
  });

  it("nie pokazuje ostrzeżenia gdy pozostało budżetu mieści się w prognozie", () => {
    render(
      <CashflowForecast
        forecast={makeForecast()}
        loading={false}
        error={false}
      />,
    );

    expect(
      screen.queryByText(/Budżety przekraczają prognozowaną płynność/),
    ).not.toBeInTheDocument();
  });

  it("pokazuje brak budżetów gdy limit wynosi zero", () => {
    render(
      <CashflowForecast
        forecast={makeForecast({
          budgets: {
            total_budget_pln: 0,
            total_spent_pln: 0,
            remaining_pln: 0,
          },
        })}
        loading={false}
        error={false}
      />,
    );

    expect(
      screen.getByText("Brak budżetów w tym miesiącu"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
