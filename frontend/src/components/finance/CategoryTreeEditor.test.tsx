import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CategoryTreeEditor } from "./CategoryTreeEditor";

const { deleteCategory, updateCategory } = vi.hoisted(() => ({
  deleteCategory: vi.fn(),
  updateCategory: vi.fn(),
}));

vi.mock("../../api/finance", () => ({
  useDeleteCategory: () => deleteCategory(),
  useUpdateCategory: () => updateCategory(),
}));

describe("CategoryTreeEditor", () => {
  it("does not normalize an untouched imported category name when saving only its color", () => {
    const mutate = vi.fn();
    updateCategory.mockReturnValue({ mutate, isPending: false });
    deleteCategory.mockReturnValue({ isPending: false });
    render(
      <CategoryTreeEditor
        onAddChild={vi.fn()}
        categories={[
          {
            id: "imported",
            name: "  Dawna nazwa  ",
            type: "expense",
            parent_id: null,
            is_active: true,
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Edytuj kategorię/ }));
    fireEvent.click(
      screen.getByRole("button", { name: /Kolor kategorii.*Niebieski/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /Zapisz kategorię/ }));
    expect(mutate).toHaveBeenCalledWith(
      { id: "imported", color: "#2563EB" },
      expect.anything(),
    );
  });
  it("saves a child override and can reset to inherited color without rewriting parent", () => {
    const mutate = vi.fn();
    updateCategory.mockReturnValue({ mutate, isPending: false });
    deleteCategory.mockReturnValue({ isPending: false });
    render(
      <CategoryTreeEditor
        onAddChild={vi.fn()}
        categories={[
          {
            id: "root",
            name: "Dom",
            type: "expense",
            parent_id: null,
            color: "#123ABC",
            is_active: true,
          },
          {
            id: "child",
            name: "Prąd",
            type: "expense",
            parent_id: "root",
            color: "#AABBCC",
            is_active: true,
          },
        ]}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Edytuj kategorię Prąd" }),
    );
    expect(screen.getByLabelText("Kolor kategorii Prąd")).toHaveValue(
      "#aabbcc",
    );
    fireEvent.change(screen.getByLabelText("Kolor kategorii Prąd"), {
      target: { value: "#fedcba" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Zapisz kategorię Prąd" }),
    );
    expect(mutate).toHaveBeenLastCalledWith(
      { id: "child", color: "#FEDCBA" },
      expect.anything(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Dziedzicz kolor" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Zapisz kategorię Prąd" }),
    );
    expect(mutate).toHaveBeenLastCalledWith(
      { id: "child", color: null },
      expect.anything(),
    );
    expect(mutate.mock.calls.every(([request]) => request.id === "child")).toBe(
      true,
    );
  });
  it("labels add-child independently and keeps active descendants under an archived ancestor", () => {
    updateCategory.mockReturnValue({ isPending: false });
    deleteCategory.mockReturnValue({ isPending: false });
    const onAddChild = vi.fn();

    render(
      <CategoryTreeEditor
        onAddChild={onAddChild}
        categories={[
          {
            id: "root",
            name: "Dom",
            type: "expense",
            parent_id: null,
            is_active: false,
          },
          {
            id: "child",
            name: "Prąd",
            type: "expense",
            parent_id: "root",
            is_active: true,
          },
        ]}
      />,
    );

    expect(
      screen.getByRole("list", { name: "Drzewo kategorii" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Prąd")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Dodaj podkategorię do Dom" }),
    );
    expect(onAddChild).toHaveBeenCalledWith("root");
  });

  it("shows a conflict error and disables the deleting row while its delete mutation is pending", () => {
    const mutate = vi.fn();
    updateCategory.mockReturnValue({ isPending: false });
    deleteCategory.mockReturnValue({
      isPending: true,
      variables: "food",
      error: { response: { status: 409, data: { detail: "has postings" } } },
      mutate,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <CategoryTreeEditor
        onAddChild={vi.fn()}
        categories={[
          {
            id: "food",
            name: "Jedzenie",
            type: "expense",
            parent_id: null,
            is_active: true,
          },
        ]}
      />,
    );

    expect(
      screen.getByText("Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Usuń kategorię Jedzenie" }),
    ).toBeDisabled();
  });

  it("renders a malformed parent cycle once without recursing indefinitely", () => {
    updateCategory.mockReturnValue({ isPending: false });
    deleteCategory.mockReturnValue({ isPending: false });

    render(
      <CategoryTreeEditor
        onAddChild={vi.fn()}
        categories={[
          {
            id: "a",
            name: "A",
            type: "expense",
            parent_id: "b",
            is_active: true,
          },
          {
            id: "b",
            name: "B",
            type: "expense",
            parent_id: "a",
            is_active: true,
          },
        ]}
      />,
    );

    expect(screen.getAllByText("A")).toHaveLength(1);
    expect(screen.getAllByText("B")).toHaveLength(1);
  });
});
