import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { processingDocument, processingReview } from "../test/documentFixtures";
import {
  useDocumentOriginal,
  useDocumentPreview,
  useDocumentReview,
  useDocumentText,
  useDocuments,
} from "./documents";

let client: QueryClient;
const owner = (id: string) => ({
  id,
  email: `${id}@example.test`,
  display_name: id,
  is_active: true,
});
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  useAuthStore.setState({
    user: owner("a"),
    authStatus: "authenticated",
    isAuthenticated: true,
    isLoading: false,
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

it.each(["original", "preview", "review", "text", "list"] as const)(
  "does not render another owner's cached %s on a retained document URL",
  async (kind) => {
    const id = processingDocument().id;
    const secret =
      kind === "original" || kind === "preview"
        ? new Blob(["synthetic-owner-a-only"])
        : kind === "review"
          ? processingReview()
          : kind === "list"
            ? [processingDocument({ user_id: "a" })]
            : { extracted_text: "synthetic-owner-a-only" };
    vi.spyOn(api, "get").mockResolvedValue({ data: secret });
    const hooks = {
      original: function useOriginal() {
        return useDocumentOriginal(id);
      },
      preview: function usePreview() {
        return useDocumentPreview(id);
      },
      review: function useReview() {
        return useDocumentReview(id);
      },
      text: function useText() {
        return useDocumentText(id);
      },
      list: function useList() {
        return useDocuments();
      },
    };
    const { result, rerender } = renderHook(() => hooks[kind](), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(secret));
    vi.mocked(api.get).mockRejectedValue({ response: { status: 404 } });
    act(() => useAuthStore.setState({ user: owner("b") }));
    rerender();
    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.isError).toBe(true));
  },
);

it("does not reuse a previous session's private blob after same-user relogin", async () => {
  const blob = new Blob(["synthetic-old-session"]);
  vi.spyOn(api, "get").mockResolvedValue({ data: blob });
  const { result, rerender } = renderHook(
    () => useDocumentOriginal(processingDocument().id),
    { wrapper },
  );
  await waitFor(() => expect(result.current.data).toBe(blob));
  vi.mocked(api.get).mockRejectedValue({ response: { status: 404 } });
  act(() => {
    useAuthStore.setState({
      user: null,
      authStatus: "unauthenticated",
      isAuthenticated: false,
    });
    useAuthStore.setState({
      user: owner("a"),
      authStatus: "authenticated",
      isAuthenticated: true,
    });
  });
  rerender();
  expect(result.current.data).toBeUndefined();
});
