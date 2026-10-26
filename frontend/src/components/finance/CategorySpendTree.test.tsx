import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CategorySpendTree } from "./CategorySpendTree";

describe("CategorySpendTree", () => {
  it("renders the selected month and category hierarchy with PLN totals", () => {
    render(
      <CategorySpendTree
        title="Wydatki według kategorii"
        loading={false}
        error={false}
        summary={{
          month: 5,
          year: 2026,
          groups: [
            {
              category_id: "transport",
              name: "Transport",
              parent_id: null,
              total_pln: 123456,
            },
          ],
          categories: [
            {
              category_id: "fuel",
              name: "Paliwo",
              parent_id: "transport",
              total_pln: 45678,
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Wydatki według kategorii" }),
    ).toBeInTheDocument();
    expect(screen.getByText("maj 2026")).toBeInTheDocument();
    expect(screen.getByText("Transport")).toBeInTheDocument();
    expect(screen.getByText("Paliwo")).toBeInTheDocument();
    expect(screen.getByText(/1.*234,56 PLN/)).toBeInTheDocument();
    expect(screen.getByText(/456,78 PLN/)).toBeInTheDocument();
  });

  it("renders deep server-provided tree totals without re-aggregating and links the rollup to the report month", () => {
    render(
      <CategorySpendTree
        title="Wydatki według kategorii"
        loading={false}
        error={false}
        summary={{
          month: 2,
          year: 2026,
          groups: [],
          categories: [],
          tree: [
            {
              category_id: "home",
              name: "Dom",
              parent_id: null,
              is_active: false,
              direct_total_pln: 1000,
              total_pln: 6000,
              children: [
                {
                  category_id: "utilities",
                  name: "Rachunki",
                  parent_id: "home",
                  is_active: true,
                  direct_total_pln: 2000,
                  total_pln: 5000,
                  children: [
                    {
                      category_id: "internet",
                      name: "Internet",
                      parent_id: "utilities",
                      is_active: true,
                      direct_total_pln: 3000,
                      total_pln: 3000,
                      children: [],
                    },
                  ],
                },
              ],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Dom")).toBeInTheDocument();
    expect(screen.getByText("Rachunki")).toBeInTheDocument();
    expect(screen.getByText("Internet")).toBeInTheDocument();
    expect(screen.getByText(/60,00 PLN/)).toBeInTheDocument();
    expect(
      screen.getByText(/w tym bezpośrednio: 10,00 PLN/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Rachunki/ })).toHaveAttribute(
      "href",
      "/finances/transactions?category_id=utilities&include_descendants=true&budget_accounts_only=true&date_from=2026-02-01&date_to=2026-02-28",
    );
    expect(screen.getByText("archiwalna")).toBeInTheDocument();
  });
});
