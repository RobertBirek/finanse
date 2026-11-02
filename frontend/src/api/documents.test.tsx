import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import {
  useDocumentReview,
  useDocuments,
  usePrepareDocumentVision,
  useRetryDocumentOcr,
} from "./documents";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => vi.restoreAllMocks());

describe("document query polling", () => {
  it("polls a technically completed document while its owner review is active", async () => {
    vi.useFakeTimers();
    const get = vi.spyOn(api, "get").mockResolvedValue({
      data: [
        {
          id: "document-1",
          status: "done",
          review: { status: "processing" },
        },
      ],
    });
    renderHook(() => useDocuments(), { wrapper });

    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    expect(get).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("stops review polling once the review is terminal", async () => {
    vi.useFakeTimers();
    const get = vi
      .spyOn(api, "get")
      .mockResolvedValueOnce({ data: { status: "pending" } })
      .mockResolvedValueOnce({ data: { status: "error" } });
    renderHook(() => useDocumentReview("document-1"), { wrapper });

    await act(async () => vi.advanceTimersByTimeAsync(3_000));
    await act(async () => vi.advanceTimersByTimeAsync(6_000));
    expect(get).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("does not poll a terminal vision review just because the historic document status is pending", async () => {
    vi.useFakeTimers();
    const get = vi.spyOn(api, "get").mockResolvedValue({
      data: [
        {
          id: "document-1",
          status: "pending",
          processing_method: "vision",
          local_ocr_state: null,
          review: {
            status: "incomplete",
            error_code: "vision_daily_limit",
            job_state: "failed",
          },
        },
      ],
    });
    renderHook(() => useDocuments(), { wrapper });

    await act(async () => vi.advanceTimersByTimeAsync(9_000));
    expect(get).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("does not poll a review after its request fails", async () => {
    vi.useFakeTimers();
    const get = vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));
    renderHook(() => useDocumentReview("document-1"), { wrapper });

    await act(async () => vi.advanceTimersByTimeAsync(9_000));
    expect(get).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});

describe("document processing intents", () => {
  it("reuses the caller's vision intent key for a transport retry", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { document_id: "document-1" },
    });
    const { result } = renderHook(() => usePrepareDocumentVision(), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        documentId: "document-1",
        intentKey: "vision-intent-1",
      });
      await result.current.mutateAsync({
        documentId: "document-1",
        intentKey: "vision-intent-1",
      });
    });

    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls.map(([, , config]) => config?.headers)).toEqual([
      { "Idempotency-Key": "vision-intent-1" },
      { "Idempotency-Key": "vision-intent-1" },
    ]);
  });

  it("keeps local OCR intent separate from vision intent", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    const vision = renderHook(() => usePrepareDocumentVision(), { wrapper });
    const ocr = renderHook(() => useRetryDocumentOcr(), { wrapper });

    await act(async () => {
      await vision.result.current.mutateAsync({
        documentId: "document-1",
        intentKey: "vision-intent-1",
      });
      await ocr.result.current.mutateAsync({
        documentId: "document-1",
        intentKey: "ocr-intent-1",
      });
    });

    expect(post).toHaveBeenNthCalledWith(
      1,
      "/documents/document-1/vision/prepare",
      undefined,
      { headers: { "Idempotency-Key": "vision-intent-1" } },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      "/documents/document-1/retry-ocr",
      undefined,
      { headers: { "Idempotency-Key": "ocr-intent-1" } },
    );
  });
});
