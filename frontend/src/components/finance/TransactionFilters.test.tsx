import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { categorySelectFixture } from "../../test/categoryFixtures";
import { TransactionFilters } from "./TransactionFilters";

it("sorts full category paths including archived filter choices, without changing the selected ID", () => {
  const apply = vi.fn();
  render(
    <TransactionFilters
      search={new URLSearchParams("category_id=water")}
      accounts={[]}
      categories={categorySelectFixture}
      onApply={apply}
      onClear={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText(/Filtry szczegółowe/));
  const select = screen.getByLabelText("Kategoria");
  expect(
    within(select)
      .getAllByRole("option")
      .map((item) => item.textContent),
  ).toEqual([
    "Wszystkie kategorie",
    "Auto (archiwalna)",
    "Auto - Zamek",
    "Dom (archiwalna)",
    "Dom - Gaz",
    "Dom - Stara (archiwalna)",
    "Dom - Woda",
    "Pensja",
  ]);
  expect(select).toHaveValue("water");
  fireEvent.change(select, { target: { value: "gas" } });
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj filtry" }));
  expect(apply.mock.calls[0][0].get("category_id")).toBe("gas");
});
