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

it("loads older documents and searches the whole selected view", async () => {
  const documents = Array.from({ length: 51 }, (_, i) =>
    processingDocument({
      id: `doc-${i + 1}`,
      original_name: `plik-${i + 1}.pdf`,
      status: "done",
      review: null,
    }),
  );
  const [oldest] = documents.slice(-1);
  const get = vi.spyOn(api, "get").mockImplementation(async (_url, config) => {
    const params = config?.params as
      { query?: string; archived?: boolean; before?: string } | undefined;
    if (params?.query) {
      return { data: params.archived ? [] : [oldest] };
    }
    if (params?.before) return { data: [oldest] };
    return { data: documents };
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DocumentList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const load = await screen.findByRole("button", { name: "Wczytaj więcej" });
  expect(screen.queryByText("plik-51.pdf")).toBeNull();
  fireEvent.click(load);
  expect(await screen.findByText("plik-51.pdf")).toBeVisible();
  expect(screen.getByText("plik-1.pdf")).toBeVisible();
  expect(get).toHaveBeenLastCalledWith(
    "/documents",
    expect.objectContaining({
      params: expect.objectContaining({ limit: 51, before: "doc-50" }),
    }),
  );
  expect(screen.queryByText("Wczytaj więcej")).toBeNull();

  fireEvent.change(
    screen.getByRole("searchbox", { name: "Szukaj po nazwie pliku" }),
    {
      target: { value: " plik-51 " },
    },
  );
  await waitFor(() => expect(screen.queryByText("plik-1.pdf")).toBeNull());
  expect(await screen.findByText("plik-51.pdf")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Archiwum" }));
  expect(
    await screen.findByText("Brak dokumentów pasujących do wyszukiwania."),
  ).toBeVisible();
  expect(get).toHaveBeenLastCalledWith(
    "/documents",
    expect.objectContaining({
      params: expect.objectContaining({
        query: "plik-51",
        archived: true,
        before: undefined,
      }),
    }),
  );
});
