import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { FinanceColorPicker } from "./FinanceColorPicker";

function EditablePicker() {
  const [color, setColor] = useState<string | null>(null);
  return (
    <FinanceColorPicker
      label="Kolor konta"
      value={color}
      previewColor="#456789"
      onChange={setColor}
    />
  );
}

describe("FinanceColorPicker", () => {
  it("allows character-by-character HEX entry including black without replacing an incomplete draft", () => {
    render(<EditablePicker />);
    const hex = screen.getByRole("textbox", { name: "Kolor konta HEX" });
    expect(hex).toHaveValue("#456789");
    for (const value of ["", "#", "#0", "#00", "#000", "#0000", "#00000"]) {
      fireEvent.change(hex, { target: { value } });
      expect(hex).toHaveValue(value);
      expect(hex).toHaveAttribute("aria-invalid", "true");
      expect(screen.getByRole("alert")).toHaveTextContent("#RRGGBB");
    }
    fireEvent.change(hex, { target: { value: "#000000" } });
    expect(hex).not.toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Kolor konta", { exact: true })).toHaveValue(
      "#000000",
    );
  });

  it("keeps text, native picker, palette and automatic reset in sync", () => {
    render(<EditablePicker />);
    const hex = screen.getByRole("textbox", { name: "Kolor konta HEX" });
    fireEvent.change(hex, { target: { value: "#a1b2c3" } });
    expect(hex).toHaveValue("#a1b2c3");
    expect(screen.getByLabelText("Kolor konta", { exact: true })).toHaveValue(
      "#a1b2c3",
    );
    fireEvent.change(screen.getByLabelText("Kolor konta", { exact: true }), {
      target: { value: "#123abc" },
    });
    expect(hex).toHaveValue("#123ABC");
    fireEvent.change(hex, { target: { value: "invalid" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Kolor konta: Niebieski" }),
    );
    expect(hex).toHaveValue("#2563EB");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.change(hex, { target: { value: "#12" } });
    fireEvent.click(screen.getByRole("button", { name: "Automatycznie" }));
    expect(hex).toHaveValue("#456789");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
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
      screen.getByRole("textbox", { name: "Kolor konta HEX" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Automatycznie" }),
    ).toHaveAttribute("aria-pressed", "true");
    for (const button of screen.getAllByRole("button"))
      expect(button).toBeDisabled();
  });
});
