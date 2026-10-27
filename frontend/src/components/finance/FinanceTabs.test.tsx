import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { FinanceTabs } from "./FinanceTabs";

describe("FinanceTabs", () => {
  it("carries only the selected period across finance tabs", () => {
    render(
      <MemoryRouter
        initialEntries={[
          "/finances/transactions?month=2&year=2026&category_id=food&detail=tx-1",
        ]}
      >
        <FinanceTabs />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Raporty" })).toHaveAttribute(
      "href",
      "/finances/reports?month=2&year=2026",
    );
    expect(screen.getByRole("link", { name: "Nadchodzące" })).toHaveAttribute(
      "href",
      "/finances/cashflow?month=2&year=2026",
    );
  });
});
