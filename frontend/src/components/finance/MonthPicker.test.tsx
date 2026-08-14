import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MonthPicker } from "./MonthPicker";

describe("MonthPicker", () => {
  it("moves to the previous month and prevents selecting a future month", () => {
    const today = new Date();
    const period = { month: today.getMonth() + 1, year: today.getFullYear() };
    const onChange = vi.fn();

    render(<MonthPicker period={period} onChange={onChange} />);

    expect(screen.getByText(/^[a-ząćęłńóśźż]+ \d{4}$/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Następny miesiąc" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Poprzedni miesiąc" }));

    expect(onChange).toHaveBeenCalledWith(
      period.month === 1
        ? { month: 12, year: period.year - 1 }
        : { month: period.month - 1, year: period.year },
    );
  });

  it("disables moving further when given a future period", () => {
    const today = new Date();
    const period =
      today.getMonth() === 11
        ? { month: 1, year: today.getFullYear() + 1 }
        : { month: today.getMonth() + 2, year: today.getFullYear() };

    render(<MonthPicker period={period} onChange={vi.fn()} />);

    expect(
      screen.getByRole("button", { name: "Następny miesiąc" }),
    ).toBeDisabled();
  });
});
