import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FinanceColorPicker } from "./FinanceColorPicker";

describe("FinanceColorPicker", () => {
  it("chooses arbitrary hex or a named swatch and can return to inherited mode", () => {
    const onChange = vi.fn();
    render(
      <FinanceColorPicker
        label="Kolor kategorii"
        value="#123ABC"
        previewColor="#456789"
        onChange={onChange}
        automaticLabel="Dziedzicz kolor"
      />,
    );
    fireEvent.change(screen.getByLabelText("Kolor kategorii"), {
      target: { value: "#aabbcc" },
    });
    expect(onChange).toHaveBeenLastCalledWith("#AABBCC");
    fireEvent.click(
      screen.getByRole("button", { name: "Kolor kategorii: Niebieski" }),
    );
    expect(onChange).toHaveBeenLastCalledWith("#2563EB");
    fireEvent.click(screen.getByRole("button", { name: "Dziedzicz kolor" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
  it("renders automatic state and disables all controls during save", () => {
    render(
      <FinanceColorPicker
        label="Kolor konta"
        value={null}
        previewColor="#456789"
        onChange={vi.fn()}
        disabled
      />,
    );
    expect(screen.getByLabelText("Kolor konta")).toHaveValue("#456789");
    expect(screen.getByLabelText("Kolor konta")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Automatycznie" }),
    ).toHaveAttribute("aria-pressed", "true");
    for (const button of screen.getAllByRole("button"))
      expect(button).toBeDisabled();
  });
});
