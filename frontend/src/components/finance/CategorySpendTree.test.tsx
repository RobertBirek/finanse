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
});
