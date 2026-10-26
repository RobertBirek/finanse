import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { CategoryRow } from "./CategorySettingsRow";

const category = {
  id: "housing",
  name: "Mieszkanie",
  parent_id: null,
  type: "expense" as const,
  is_active: true,
};

function props(
  overrides: Partial<ComponentProps<typeof CategoryRow>> = {},
): ComponentProps<typeof CategoryRow> {
  return {
    category,
    categories: [category],
    updateMutation: {
      mutate: vi.fn(),
      isPending: false,
      variables: undefined,
      error: null,
    } as never,
    deleteMutation: {
      mutate: vi.fn(),
      isPending: false,
      variables: "housing",
      error: { response: { status: 409 } },
    } as never,
    editing: false,
    onStartEdit: vi.fn(),
    onCancelEdit: vi.fn(),
    ...overrides,
  };
}

describe("CategoryRow deletion safety", () => {
  it("keeps the conflict warning for a category with records", () => {
    render(<CategoryRow {...props()} />);
    expect(
      screen.getByText("Kategoria ma zapisy — zdezaktywuj ją zamiast usuwać"),
    ).toBeInTheDocument();
  });

  it("does not call delete unless the user confirms", () => {
    const remove = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <CategoryRow
        {...props({
          deleteMutation: {
            mutate: remove,
            isPending: false,
            variables: undefined,
            error: null,
          } as never,
        })}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Usuń kategorię Mieszkanie" }),
    );
    expect(remove).not.toHaveBeenCalled();
  });
});
