import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import {
  useDocumentProcessingStore as store,
  captureProcessingActor,
} from "../../stores/documentProcessingStore";
import { processingDocument } from "../../test/documentFixtures";
import { Layout } from "../Layout";
import { usePrepareDocumentVision } from "../../api/documents";

let document = processingDocument();
let client: QueryClient;
let activePages: number[] = [];
function Page() {
  const mutation = usePrepareDocumentVision();
  const location = useLocation();
  return (
    <>
      <Link to="/other">Inna strona</Link>
      <button
        onClick={() =>
          mutation.mutate({
            documentId: document.id,
            intentKey: "explicit-intent",
          })
        }
      >
        Uruchom odczyt
      </button>
      <p>
        {location.pathname}
        {location.search}
      </p>
    </>
  );
}
function mount() {
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/documents"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="documents" element={<Page />} />
              <Route path="other" element={<Page />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}
beforeEach(() => {
  document = processingDocument();
  activePages = [];
  useAuthStore.setState({
    user: {
      id: "owner",
      email: "synthetic@example.test",
      display_name: "Synthetic",
      is_active: true,
    },
    authStatus: "authenticated",
    isAuthenticated: true,
    isLoading: false,
  });
  store.getState().bindOwner(null);
  store.getState().bindOwner("owner");
  vi.spyOn(api, "get").mockImplementation(async (url, config) => {
    if (url === "/documents/active") {
      activePages.push(
        (config?.params as { offset?: number } | undefined)?.offset ?? 0,
      );
      return {
        data: document.review?.job_state === "processing" ? [document] : [],
      };
    }
    if (url === `/documents/${document.id}`) return { data: document };
    return { data: [] };
  });
  vi.spyOn(api, "post").mockImplementation(async () => ({
    data: {
      id: document.review!.revision_id,
      document_id: document.id,
      status: "pending",
      input_method: "image",
      revision: 1,
      fields: {},
      warnings: [],
    },
  }));
});
afterEach(() => {
  client?.clear();
  vi.restoreAllMocks();
  store.getState().bindOwner(null);
  useAuthStore.setState({
    user: null,
    authStatus: "unauthenticated",
    isAuthenticated: false,
  });
});

describe("global processing feedback", () => {
  it("discovers every page of active work, not only the default fifty documents", async () => {
    const documents = Array.from({ length: 101 }, (_, i) =>
      processingDocument({
        id: `${i.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`,
        review: { ...document.review!, revision_id: `revision-${i}` },
      }),
    );
    vi.mocked(api.get).mockImplementation(async (url, config) => {
      if (url === "/documents/active") {
        const offset =
          (config?.params as { offset?: number } | undefined)?.offset ?? 0;
        activePages.push(offset);
        return { data: documents.slice(offset, offset + 100) };
      }
      return { data: documents.find((d) => url === `/documents/${d.id}`) };
    });
    mount();
    await waitFor(() =>
      expect(Object.keys(store.getState().watches)).toHaveLength(101),
    );
    expect(activePages).toContain(100);
    expect(screen.getByLabelText("Przetwarzanie dokumentów")).toHaveTextContent(
      "AI pracuje (101)",
    );
  });
  it("reports an unavailable status without declaring completion, then recovers", async () => {
    mount();
    await screen.findByLabelText("Przetwarzanie dokumentów");
    vi.mocked(api.get).mockRejectedValue(new Error("synthetic-offline"));
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    expect(
      await screen.findByLabelText("Przetwarzanie dokumentów"),
    ).toHaveTextContent("Status odczytu chwilowo niedostępny");
    expect(store.getState().toasts).toHaveLength(0);
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
    expect(Object.values(store.getState().watches)[0].state).toBe("unknown");
    document = {
      ...document,
      review: { ...document.review!, status: "ready", job_state: "succeeded" },
    };
    vi.mocked(api.get).mockImplementation(async (url) => ({
      data: url === "/documents/active" ? [] : document,
    }));
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    expect(
      await screen.findByText("Propozycja z AI gotowa — sprawdź dane."),
    ).toBeVisible();
    expect(api.post).not.toHaveBeenCalled();
  });
  it("removes a disappeared document without a false completion toast", async () => {
    mount();
    await screen.findByLabelText("Przetwarzanie dokumentów");
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (url === "/documents/active") return { data: [] };
      throw { response: { status: 404 } };
    });
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    await waitFor(() =>
      expect(Object.keys(store.getState().watches)).toHaveLength(0),
    );
    expect(store.getState().toasts).toHaveLength(0);
    expect(
      screen.queryByLabelText("Przetwarzanie dokumentów"),
    ).not.toBeInTheDocument();
  });
  it("uses the batched active snapshot instead of polling every still-active document separately", async () => {
    mount();
    await screen.findByLabelText("Przetwarzanie dokumentów");
    expect(api.get).not.toHaveBeenCalledWith(
      `/documents/${document.id}`,
      expect.anything(),
    );
  });
  it("keeps progress across navigation, then shows one dismissible completion toast with an open action", async () => {
    mount();
    expect(
      await screen.findByLabelText("Przetwarzanie dokumentów"),
    ).toHaveTextContent("AI pracuje");
    fireEvent.click(screen.getByText("Inna strona"));
    expect(screen.getByLabelText("Przetwarzanie dokumentów")).toHaveTextContent(
      "AI pracuje",
    );
    document = {
      ...document,
      review: { ...document.review!, status: "ready", job_state: "succeeded" },
    };
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    expect(
      await screen.findByText("Propozycja z AI gotowa — sprawdź dane."),
    ).toBeVisible();
    expect(
      screen.getAllByRole("link", { name: "Otwórz dokument" }),
    ).toHaveLength(1);
    fireEvent.click(screen.getByRole("link", { name: "Otwórz dokument" }));
    expect(
      await screen.findByText(`/documents?review=${document.id}`),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Zamknij powiadomienie" }),
    );
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    expect(
      screen.queryByText("Propozycja z AI gotowa — sprawdź dane."),
    ).not.toBeInTheDocument();
  });
  it("never toasts completed history but does toast an accepted fast job", async () => {
    document = {
      ...document,
      review: { ...document.review!, status: "ready", job_state: "succeeded" },
    };
    mount();
    await waitFor(() => expect(activePages.length).toBeGreaterThan(0));
    expect(
      screen.queryByText("Propozycja z AI gotowa — sprawdź dane."),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Uruchom odczyt"));
    expect(
      await screen.findByText("Propozycja z AI gotowa — sprawdź dane."),
    ).toBeVisible();
    expect(api.post).toHaveBeenCalledTimes(1);
  });
  it("continues to track a known document when the active discovery list no longer contains it", async () => {
    mount();
    await screen.findByLabelText("Przetwarzanie dokumentów");
    document = {
      ...document,
      local_ocr_job_id: "ocr-id",
      local_ocr_state: "processing",
      review: { ...document.review!, status: "ready", job_state: "succeeded" },
    };
    const actor = captureProcessingActor();
    act(() =>
      store.getState().register(actor, {
        key: "ocr:ocr-id",
        operationId: "ocr:ocr-id",
        documentId: document.id,
        source: "local_ocr",
        kind: "ocr",
      }),
    );
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    await waitFor(() =>
      expect(
        screen.getByLabelText("Przetwarzanie dokumentów"),
      ).toHaveTextContent("OCR pracuje"),
    );
    document = { ...document, local_ocr_state: "succeeded" };
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    expect(
      await screen.findByText("OCR zakończony — sprawdź odczyt."),
    ).toBeVisible();
  });
  it("clears visible feedback when the authenticated owner changes", async () => {
    mount();
    await screen.findByLabelText("Przetwarzanie dokumentów");
    document = {
      ...document,
      review: { ...document.review!, status: "ready", job_state: "succeeded" },
    };
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["documents"] });
    });
    await screen.findByText("Propozycja z AI gotowa — sprawdź dane.");
    act(() =>
      useAuthStore.setState({
        user: {
          id: "other",
          email: "other@example.test",
          display_name: "Other",
          is_active: true,
        },
      }),
    );
    expect(
      screen.queryByText("Propozycja z AI gotowa — sprawdź dane."),
    ).not.toBeInTheDocument();
  });
});
