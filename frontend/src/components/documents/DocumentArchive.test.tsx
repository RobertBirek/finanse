import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { processingDocument } from "../../test/documentFixtures";
import { DocumentList } from "../DocumentList";
import { DocumentUpload } from "../DocumentUpload";

let doc = processingDocument();
let archived = false;
let client: QueryClient;
const stamp = "2026-11-03T12:00:00Z";
beforeEach(() => {
  archived = false;
  doc = processingDocument();
  doc.review = { ...doc.review!, status: "ready", job_state: "succeeded" };
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "fixture@example.test",
      display_name: "Fixture",
      is_active: true,
    },
    authStatus: "authenticated",
    isAuthenticated: true,
    isLoading: false,
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "get").mockImplementation(async (url, config) => {
    if (url === "/documents")
      return {
        data:
          !!(config?.params as { archived?: boolean })?.archived === archived
            ? [{ ...doc, archived_at: archived ? stamp : null }]
            : [],
      };
    if (String(url).endsWith("upload-capabilities"))
      return {
        data: {
          max_file_bytes: 1000,
          accepted_mime_types: ["image/jpeg"],
          automatic_image_vision: false,
        },
      };
    return { data: { ...doc, archived_at: archived ? stamp : null } };
  });
  vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("/archive")) archived = true;
    else if (String(url).endsWith("/restore")) archived = false;
    else if (url === "/documents/upload")
      return {
        data: { document: { ...doc, archived_at: stamp }, is_duplicate: true },
      };
    else throw new Error("Unexpected mutation");
    return { data: { ...doc, archived_at: archived ? stamp : null } };
  });
});
afterEach(() => {
  client.clear();
  vi.restoreAllMocks();
  useAuthStore.setState({
    user: null,
    authStatus: "unauthenticated",
    isAuthenticated: false,
  });
});
const mount = (element = <DocumentList />) =>
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );

it("archives, lists the archive and restores without DELETE or new AI/OCR", async () => {
  mount();
  fireEvent.click(
    await screen.findByRole("button", {
      name: `Archiwizuj dokument: ${doc.original_name}`,
    }),
  );
  expect(window.confirm).toHaveBeenCalledWith(
    "Przenieść dokument do archiwum? Plik, historia odczytu i powiązania finansowe pozostaną zachowane.",
  );
  expect(
    await screen.findByText("Dokument przeniesiony do archiwum."),
  ).toBeVisible();
  await waitFor(() =>
    expect(
      screen.queryByRole("button", {
        name: `Otwórz dokument: ${doc.original_name}`,
      }),
    ).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Archiwum" }));
  fireEvent.click(
    await screen.findByRole("button", {
      name: `Przywróć dokument: ${doc.original_name}`,
    }),
  );
  expect(await screen.findByText("Dokument przywrócony.")).toBeVisible();
  expect(api.post).toHaveBeenCalledTimes(2);
  expect(api.post).toHaveBeenCalledWith(`/documents/${doc.id}/archive`);
  expect(api.post).toHaveBeenCalledWith(`/documents/${doc.id}/restore`);
});

it("explains active processing instead of offering a blind retry", async () => {
  vi.mocked(api.post).mockRejectedValue({
    response: { status: 409, data: { code: "document_processing_active" } },
  });
  mount();
  fireEvent.click(
    await screen.findByRole("button", {
      name: `Archiwizuj dokument: ${doc.original_name}`,
    }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Dokument jest przetwarzany. Poczekaj na zakończenie odczytu AI/OCR.",
  );
  expect(
    screen.getByRole("button", {
      name: `Otwórz dokument: ${doc.original_name}`,
    }),
  ).toBeVisible();
});

it("does not archive after confirmation is declined", async () => {
  vi.mocked(window.confirm).mockReturnValue(false);
  mount();
  fireEvent.click(
    await screen.findByRole("button", {
      name: `Archiwizuj dokument: ${doc.original_name}`,
    }),
  );
  expect(api.post).not.toHaveBeenCalled();
});

it("offers explicit restore for an archived duplicate upload, never auto-restores", async () => {
  const { container } = mount(<DocumentUpload />);
  fireEvent.change(container.querySelector('input[type="file"]')!, {
    target: {
      files: [new File(["synthetic"], "fixture.jpg", { type: "image/jpeg" })],
    },
  });
  expect(
    await screen.findByText(
      "Ten plik jest już w archiwum. Możesz go przywrócić.",
    ),
  ).toBeVisible();
  expect(api.post).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Przywróć" }));
  await waitFor(() =>
    expect(api.post).toHaveBeenCalledWith(`/documents/${doc.id}/restore`),
  );
  expect(api.post).toHaveBeenCalledTimes(2);
});
