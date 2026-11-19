import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { processingDocument, processingReview } from "../test/documentFixtures";
import { DocumentList } from "./DocumentList";

afterEach(() => vi.restoreAllMocks());

it("shows independent finance evidence even if the latest recognition failed", async () => {
  const document = processingDocument({
    status: "error",
    review: null,
    finance: {
      state: "succeeded",
      bill_id: "bill-owned",
      review: "approved",
      lifecycle: "active",
    },
  });
  vi.spyOn(api, "get").mockResolvedValue({ data: [document] });
  const post = vi.spyOn(api, "post");
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <DocumentList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("img", { name: /^Odczyt · Błąd/ }),
  ).toBeVisible();
  expect(
    screen.getByRole("img", { name: "Finanse · Zatwierdzony" }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Otwórz w finansach" }),
  ).toHaveAttribute("href", "/finances/documents?bill=bill-owned");
  expect(post).not.toHaveBeenCalled();
});

it("does not invent a finance link from ready OCR", async () => {
  const document = processingDocument({
    review: {
      ...processingDocument().review!,
      status: "ready",
      job_state: "succeeded",
    },
  });
  vi.spyOn(api, "get").mockResolvedValue({ data: [document] });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <DocumentList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("img", { name: "Finanse · Nie wczytano" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Otwórz w finansach" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sprawdź dane" })).toBeVisible();
});
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
  await waitFor(() =>
    expect(screen.getByLabelText("Sprzedawca")).toHaveValue("Synthetic"),
  );
  fireEvent.click(screen.getByRole("button", { name: "Zamknij" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(post).not.toHaveBeenCalled();
  client.clear();
});
