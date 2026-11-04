import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, it, expect, vi } from "vitest";
import api from "../lib/api";
import { FinanceCategoryProposals } from "./FinanceCategoryProposals";
beforeEach(() => vi.restoreAllMocks());
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <FinanceCategoryProposals />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("failed queue read is not an empty queue", async () => {
  vi.spyOn(api, "get").mockRejectedValue(new Error("Offline"));
  mount();
  await screen.findByText("Nie udało się pobrać propozycji.");
  expect(
    screen.queryByText("Brak propozycji do przejrzenia."),
  ).not.toBeInTheDocument();
});
it("empty queue distinguishes pending analyses and explains month-independent scope", async () => {
  vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/proposals")
      ? { items: [], next_cursor: null, page_size: 20 }
      : String(url).endsWith("/activity")
        ? {
            active_jobs: [{ id: "j", state: "ready" }],
            recent_outcomes: [],
            poll_after_ms: 2000,
          }
        : [],
  }));
  mount();
  await screen.findByText("Brak propozycji do przejrzenia.");
  expect(
    await screen.findByText(/Trwa analiza nowych wydatków/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Nie filtrujemy tej kolejki według miesiąca/),
  ).toBeInTheDocument();
});
