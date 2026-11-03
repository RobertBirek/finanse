import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { useDocumentProcessingStore as store } from "../stores/documentProcessingStore";
import { processingDocument, processingReview } from "../test/documentFixtures";
import {
  documentQueryKey,
  useArchiveDocument,
  useRestoreDocument,
  usePrepareDocumentReview,
  usePrepareDocumentVision,
  useRetryDocumentOcr,
  useUploadDocument,
  type DocumentReview,
} from "./documents";

let client: QueryClient;
const user = {
  id: "owner",
  email: "synthetic@example.test",
  display_name: "Synthetic",
  is_active: true,
};
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={client}>{children}</QueryClientProvider>
);
beforeEach(() => {
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  useAuthStore.setState({
    user,
    authStatus: "authenticated",
    isAuthenticated: true,
    isLoading: false,
  });
  store.getState().bindOwner(null);
  store.getState().bindOwner(user.id);
});
afterEach(() => {
  client.clear();
  vi.restoreAllMocks();
  store.getState().bindOwner(null);
  useAuthStore.setState({
    user: null,
    authStatus: "unauthenticated",
    isAuthenticated: false,
  });
});

describe("accepted document operations", () => {
  it("clears archived feedback and restores without creating processing work", async () => {
    vi.spyOn(api, "post")
      .mockResolvedValueOnce({
        data: processingDocument({ archived_at: "2026-11-03T12:00:00Z" }),
      })
      .mockResolvedValueOnce({
        data: processingDocument({ archived_at: null }),
      });
    const actor = { ownerId: "owner", generation: store.getState().generation };
    store
      .getState()
      .observeDocument(actor, processingDocument(), store.getState().sequence);
    const { result } = renderHook(
      () => ({ archive: useArchiveDocument(), restore: useRestoreDocument() }),
      { wrapper },
    );
    await act(async () => {
      await result.current.archive.mutateAsync({
        documentId: processingDocument().id,
      });
    });
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    await act(async () => {
      await result.current.restore.mutateAsync({
        documentId: processingDocument().id,
      });
    });
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    expect(api.post).toHaveBeenCalledTimes(2);
  });
  it.each([true, false])(
    "fences a late archive after logout/relogin sameUser=%s",
    async (sameUser) => {
      let resolve!: (reply: {
        data: ReturnType<typeof processingDocument>;
      }) => void;
      vi.spyOn(api, "post").mockReturnValue(
        new Promise((r) => {
          resolve = r;
        }),
      );
      const { result } = renderHook(() => useArchiveDocument(), { wrapper });
      let pending!: Promise<unknown>;
      act(() => {
        pending = result.current.mutateAsync({
          documentId: processingDocument().id,
        });
      });
      await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
      useAuthStore.setState({
        user: null,
        authStatus: "unauthenticated",
        isAuthenticated: false,
      });
      const owner = sameUser ? user : { ...user, id: "other" };
      useAuthStore.setState({
        user: owner,
        authStatus: "authenticated",
        isAuthenticated: true,
      });
      const actor = {
        ownerId: owner.id,
        generation: store.getState().generation,
      };
      store
        .getState()
        .observeDocument(
          actor,
          processingDocument({ user_id: owner.id }),
          store.getState().sequence,
        );
      await act(async () => {
        resolve({
          data: processingDocument({ archived_at: "2026-11-03T12:00:00Z" }),
        });
        await pending;
      });
      expect(Object.keys(store.getState().watches)).toHaveLength(1);
      expect(
        client.getQueryData(
          documentQueryKey(processingDocument().id, "metadata", {
            ownerId: owner.id,
            generation: store.getState().generation,
          }),
        ),
      ).toBeUndefined();
    },
  );
  it("registers a known vision revision and preserves the review cache", async () => {
    const review = processingReview();
    vi.spyOn(api, "post").mockResolvedValue({ data: review });
    const { result } = renderHook(() => usePrepareDocumentVision(), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({
        documentId: review.document_id,
        intentKey: "one",
      });
    });
    expect(Object.values(store.getState().watches)).toEqual([
      expect.objectContaining({
        operationId: `review:${review.id}`,
        documentId: review.document_id,
        kind: "ai",
      }),
    ]);
    expect(
      client.getQueryData(
        documentQueryKey(review.document_id, "review", {
          ownerId: "owner",
          generation: store.getState().generation,
        }),
      ),
    ).toEqual(review);
    expect(api.post).toHaveBeenCalledTimes(1);
  });
  it("does not register duplicate upload as new work", async () => {
    vi.spyOn(api, "post").mockResolvedValue({
      data: { document: processingDocument(), is_duplicate: true },
    });
    const { result } = renderHook(() => useUploadDocument(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(
        new File(["synthetic"], "synthetic.jpg"),
      );
    });
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
  it("registers a new upload even before its first revision summary arrives", async () => {
    const doc = processingDocument({ status: "pending", review: null });
    vi.spyOn(api, "post").mockResolvedValue({
      data: { document: doc, is_duplicate: false },
    });
    const { result } = renderHook(() => useUploadDocument(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(
        new File(["synthetic"], "synthetic.jpg"),
      );
    });
    expect(Object.values(store.getState().watches)).toEqual([
      expect.objectContaining({
        documentId: doc.id,
        kind: "ai",
        source: "review",
      }),
    ]);
  });
  it.each([true, false])(
    "fences a late revision after logout/user switch (sameUser=%s)",
    async (sameUser) => {
      let resolve!: (value: { data: DocumentReview }) => void;
      const reply = new Promise<{ data: DocumentReview }>((r) => {
        resolve = r;
      });
      vi.spyOn(api, "post").mockReturnValue(reply);
      const { result } = renderHook(() => usePrepareDocumentVision(), {
        wrapper,
      });
      let pending!: Promise<DocumentReview>;
      act(() => {
        pending = result.current.mutateAsync({
          documentId: processingReview().document_id,
          intentKey: "old",
        });
      });
      await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
      act(() => {
        useAuthStore.setState({
          user: null,
          authStatus: "unauthenticated",
          isAuthenticated: false,
        });
        useAuthStore.setState({
          user: sameUser ? user : { ...user, id: "other" },
          authStatus: "authenticated",
          isAuthenticated: true,
        });
      });
      await act(async () => {
        resolve({ data: processingReview() });
        await pending;
      });
      expect(Object.keys(store.getState().watches)).toHaveLength(0);
      expect(
        client.getQueryData(
          documentQueryKey(processingReview().document_id, "review", {
            ownerId: useAuthStore.getState().user?.id ?? null,
            generation: store.getState().generation,
          }),
        ),
      ).toBeUndefined();
    },
  );
  it("uses the actual local OCR job ID and a fresh legacy intent key", async () => {
    const { result } = renderHook(() => useRetryDocumentOcr(), { wrapper });
    vi.spyOn(api, "post")
      .mockResolvedValueOnce({
        data: { id: "doc-local", status: "pending", job_id: "ocr-id" },
      })
      .mockResolvedValueOnce({ data: { id: "doc-legacy", status: "pending" } });
    await act(async () => {
      await result.current.mutateAsync({
        documentId: "doc-local",
        intentKey: "local",
      });
      await result.current.mutateAsync({
        documentId: "doc-legacy",
        intentKey: "new-legacy-intent",
      });
    });
    expect(Object.values(store.getState().watches)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          operationId: "ocr:ocr-id",
          source: "local_ocr",
        }),
        expect.objectContaining({
          key: "legacy:doc-legacy:new-legacy-intent",
          source: "legacy_ocr",
        }),
      ]),
    );
  });
  it("does not register a pre-existing ready text review on prepare without refresh", async () => {
    vi.spyOn(api, "post").mockResolvedValue({
      data: processingReview({ status: "ready", input_method: "text" }),
    });
    const { result } = renderHook(() => usePrepareDocumentReview(), {
      wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync({
        documentId: processingReview().document_id,
        refresh: false,
      });
    });
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
});
