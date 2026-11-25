import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AccountStrip } from "./AccountStrip";

vi.mock("../../api/finance", () => ({
  useAccounts: () => ({
    data: [
      {
        id: "a",
        name: "PLN",
        currency: "PLN",
        balance_source: 12345,
        balance_pln: 12345,
      },
      {
        id: "b",
        name: "Euro",
        currency: "EUR",
        balance_source: 101,
        balance_pln: 440,
      },
      {
        id: "c",
        name: "Archiwum",
        currency: "PLN",
        balance_source: 0,
        is_active: false,
      },
    ],
  }),
}));

function Location() {
  const location = useLocation();
  return <output aria-label="Adres">{location.search}</output>;
}

it("toggles the shared account filter while preserving the other filters and resetting the page", () => {
  render(
    <MemoryRouter
      initialEntries={["/finances/transactions?q=kawa&page=3&account_id=a"]}
    >
      <AccountStrip mode="filter" />
      <Location />
    </MemoryRouter>,
  );
  const first = screen.getByRole("button", { name: /PLN.*123,45 PLN/ });
  const second = screen.getByRole("button", { name: /Euro.*1,01 EUR/ });
  expect(first).toHaveAttribute("aria-pressed", "true");
  expect(
    screen.queryByRole("button", { name: /Archiwum/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(second);
  expect(second).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Adres")).toHaveTextContent(
    "?q=kawa&account_id=b",
  );
  fireEvent.click(second);
  expect(second).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByLabelText("Adres")).toHaveTextContent("?q=kawa");
});
