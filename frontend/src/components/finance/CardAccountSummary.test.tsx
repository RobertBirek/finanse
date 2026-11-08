import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CardAccountSummary } from "./CardAccountSummary";
import { useCreditCard } from "../../api/creditCards";
vi.mock("../../api/creditCards", () => ({ useCreditCard: vi.fn() }));
it("shows server card limit/debt and links to the same account", () => {
  vi.mocked(useCreditCard).mockReturnValue({
    data: { limit_pln: 3360000, debt_pln: 102796, available_pln: 3257204 },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useCreditCard>);
  render(<CardAccountSummary accountId="card" />);
  expect(screen.getByText(/32\s?572,04/)).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Rozliczenia karty/ }),
  ).toHaveAttribute("href", "/settings/finances/cards/card");
});
it("does not report a failed fetch as zero debt", () => {
  vi.mocked(useCreditCard).mockReturnValue({ isError: true } as ReturnType<
    typeof useCreditCard
  >);
  render(<CardAccountSummary accountId="card" />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Nie udało się pobrać limitu",
  );
  expect(screen.queryByText(/0,00 PLN/)).not.toBeInTheDocument();
});
