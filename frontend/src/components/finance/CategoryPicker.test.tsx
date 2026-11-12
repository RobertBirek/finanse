import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CategoryPicker } from "./CategoryPicker";
import { categorySelectFixture } from "../../test/categoryFixtures";

const categories = [
  {
    id: "home",
    name: "Dom",
    parent_id: null,
    type: "expense" as const,
    is_active: true,
  },
  {
    id: "rent",
    name: "Czynsz",
    parent_id: "home",
    type: "expense" as const,
    is_active: true,
  },
  {
    id: "old",
    name: "Stary czynsz",
    parent_id: "home",
    type: "expense" as const,
    is_active: false,
  },
  {
    id: "salary",
    name: "Pensja",
    parent_id: null,
    type: "income" as const,
    is_active: true,
  },
];

describe("CategoryPicker", () => {
  it("receipt search excludes a selected nonmatching category without changing its value", () => {
    const change = vi.fn();
    const view = render(
      <CategoryPicker
        id="receipt-category"
        categories={categories}
        value="home"
        onChange={change}
        type="expense"
        retainSelectedOption={false}
      />,
    );
    fireEvent.change(screen.getByLabelText("Szukaj: Kategoria"), {
      target: { value: "czynsz" },
    });
    const select = screen.getByLabelText("Kategoria");
    expect(
      within(select).queryByRole("option", { name: /^Dom$/ }),
    ).not.toBeInTheDocument();
    expect(change).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Szukaj: Kategoria"), {
      target: { value: "zzzz" },
    });
    expect(screen.getByText("Brak pasujących kategorii")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Szukaj: Kategoria"), {
      target: { value: "" },
    });
    expect(
      within(select).getByRole("option", { name: /^Dom$/ }),
    ).toBeInTheDocument();
    view.unmount();
  });
  it("searches hierarchy paths, filters by transaction type and excludes archived items", () => {
    const onChange = vi.fn();
    render(
      <CategoryPicker
        id="category"
        categories={categories}
        value=""
        onChange={onChange}
        type="expense"
      />,
    );

    const select = screen.getByLabelText("Kategoria");
    expect(
      within(select).getByRole("option", { name: "Dom - Czynsz" }),
    ).toBeInTheDocument();
    expect(
      within(select).queryByRole("option", { name: /Pensja/ }),
    ).not.toBeInTheDocument();
    expect(
      within(select).queryByRole("option", { name: /Stary czynsz/ }),
    ).not.toBeInTheDocument();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Szukaj: Kategoria" }),
      { target: { value: "czynsz" } },
    );
    expect(
      within(select).queryByRole("option", { name: "Dom" }),
    ).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "rent" } });
    expect(onChange).toHaveBeenCalledWith("rent");
  });

  it("can deliberately include archived categories with their visible status", () => {
    render(
      <CategoryPicker
        id="category"
        categories={categories}
        value="old"
        onChange={vi.fn()}
        includeInactive
      />,
    );
    expect(
      screen.getByRole("option", { name: "Dom - Stary czynsz (archiwalna)" }),
    ).toBeInTheDocument();
  });

  it("sorts full labels but keeps the selected ID and type/archive rules", () => {
    const change = vi.fn();
    render(
      <CategoryPicker
        id="paths"
        categories={categorySelectFixture}
        value="water"
        onChange={change}
        type="expense"
      />,
    );
    const select = screen.getByLabelText("Kategoria");
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Wybierz kategorię", "Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
    expect(select).toHaveValue("water");
    expect(change).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Szukaj: Kategoria"), {
      target: { value: "Dom - Gaz" },
    });
    expect(
      within(select).getByRole("option", { name: "Dom - Gaz" }),
    ).toBeInTheDocument();
    expect(select).toHaveValue("water");
    fireEvent.change(select, { target: { value: "gas" } });
    expect(change).toHaveBeenCalledWith("gas");
  });

  it("keeps full ancestry when the caller has already filtered the available choices", () => {
    render(
      <CategoryPicker
        id="filtered"
        categories={categorySelectFixture.filter(
          (c) => c.is_active && c.type === "expense",
        )}
        hierarchyCategories={categorySelectFixture}
        value=""
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["Wybierz kategorię", "Auto - Zamek", "Dom - Gaz", "Dom - Woda"]);
  });
});
