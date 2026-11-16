import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { OpeningBalanceFields } from "./OpeningBalanceFields";

function Fields({ currency = "PLN" }: { currency?: string }) {
  const [value, onChange] = useState({
    amount: "",
    date: "2026-11-16",
    fxRate: "",
  });
  return (
    <OpeningBalanceFields
      value={value}
      onChange={onChange}
      currency={currency}
    />
  );
}

describe("BO fields", () => {
  it("accepts a minus sign and shows the selected date", () => {
    render(<Fields />);
    const amount = screen.getByLabelText("Kwota BO (PLN)");
    fireEvent.change(amount, { target: { value: "-123,45" } });
    expect(amount).toHaveValue("-123,45");
    expect(screen.getByLabelText("Data BO")).toHaveValue("2026-11-16");
  });
  it("asks for an FX quote only for a nonzero foreign opening balance", () => {
    render(<Fields currency="EUR" />);
    expect(
      screen.queryByLabelText("Kurs BO (PLN za 1 EUR)"),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Kwota BO (EUR)"), {
      target: { value: "-10" },
    });
    expect(screen.getByLabelText("Kurs BO (PLN za 1 EUR)")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Kwota BO (EUR)"), {
      target: { value: "0" },
    });
    expect(
      screen.queryByLabelText("Kurs BO (PLN za 1 EUR)"),
    ).not.toBeInTheDocument();
  });
});
