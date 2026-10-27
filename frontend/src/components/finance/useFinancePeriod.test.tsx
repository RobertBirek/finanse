import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useFinancePeriod } from "./useFinancePeriod";

function PeriodHarness() {
  const [period, setPeriod] = useFinancePeriod();
  const location = useLocation();
  return (
    <>
      <p>{`${period.year}-${period.month}`}</p>
      <p data-testid="search">{location.search}</p>
      <button type="button" onClick={() => setPeriod({ month: 3, year: 2026 })}>
        Zmień miesiąc
      </button>
    </>
  );
}

describe("useFinancePeriod", () => {
  it("reads a valid period from the URL and preserves unrelated parameters when changing it", () => {
    render(
      <MemoryRouter
        initialEntries={["/finances/reports?month=2&year=2026&view=tree"]}
      >
        <PeriodHarness />
      </MemoryRouter>,
    );

    expect(screen.getByText("2026-2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Zmień miesiąc" }));
    expect(screen.getByTestId("search")).toHaveTextContent(
      "?month=3&year=2026&view=tree",
    );
  });

  it("falls back to the current period for incomplete or backend-invalid URL values", () => {
    const today = new Date();
    render(
      <MemoryRouter initialEntries={["/finances?month=13&year=1999"]}>
        <PeriodHarness />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(`${today.getFullYear()}-${today.getMonth() + 1}`),
    ).toBeInTheDocument();
  });
});
