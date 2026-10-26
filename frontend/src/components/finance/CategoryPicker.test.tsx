import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CategoryPicker } from "./CategoryPicker";

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
      within(select).getByRole("option", { name: "Dom → Czynsz" }),
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
      screen.getByRole("option", { name: "Dom → Stary czynsz (archiwalna)" }),
    ).toBeInTheDocument();
  });
});
