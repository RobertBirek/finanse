import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { processingReview } from "../test/documentFixtures";
import { DocumentList } from "./DocumentList";

afterEach(() => vi.restoreAllMocks());
it("opens a toast-linked review even when the document is outside the current list page", async () => {
  const review = processingReview({ status: "ready" });
  vi.spyOn(api, "get").mockImplementation(async (url) => {
    if (url === `/documents/${review.document_id}/review`)
      return { data: review };
    if (String(url).endsWith("/preview") || String(url).endsWith("/original"))
      throw { response: { status: 404 } };
    return { data: [] };
  });
  const post = vi.spyOn(api, "post");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`/documents?review=${review.document_id}`]}
      >
        <DocumentList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("dialog", { name: "Sprawdź dane dokumentu" }),
  ).toBeVisible();
  expect(await screen.findByLabelText("Sprzedawca")).toHaveValue("Synthetic");
  fireEvent.click(screen.getByRole("button", { name: "Zamknij" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(post).not.toHaveBeenCalled();
  client.clear();
});
