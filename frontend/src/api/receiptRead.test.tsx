import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import {
  useStartReceiptRead,
  useReceiptReadJob,
  useImportReceiptRead,
} from "./receiptRead";
import { readJob } from "../components/finance/receipts/receiptReadTestData";
import { useAttachBillSource } from "./bills";
beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 55 });
});
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}
it("source changes invalidate receipt read eligibility", async () => {
  vi.spyOn(api, "post").mockResolvedValue({ data: {} });
  const env = setup();
  const invalidate = vi.spyOn(env.client, "invalidateQueries");
  const hook = renderHook(() => useAttachBillSource(), env);
  await act(async () => {
    await hook.result.current.mutateAsync({
      billId: "bill",
      documentId: "photo",
      expectedVersion: 1,
      idempotencyKey: "k",
    });
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["finance", "receipt-read"],
  });
});
it("read writes strip client authority and never retry on network failure", async () => {
  const post = vi.spyOn(api, "post").mockRejectedValue(new Error("Lost"));
  const env = setup();
  const hook = renderHook(() => useStartReceiptRead(), env);
  const input = {
    session: 55,
    billId: "bill",
    key: "one-intent",
    body: {
      document_id: "photo",
      expected_export_snapshot: "a".repeat(64),
      confirmed: true,
    },
  };
  await act(async () => {
    await expect(hook.result.current.mutateAsync(input)).rejects.toThrow(
      "Lost",
    );
  });
  expect(post).toHaveBeenCalledExactlyOnceWith(
    "/finance/bills/bill/items/read-start",
    input.body,
    { headers: { "Idempotency-Key": "one-intent" } },
  );
  useAuthStore.setState({ sessionVersion: 56 });
  await act(async () => {
    await expect(hook.result.current.mutateAsync(input)).rejects.toThrow(
      "session_changed",
    );
  });
  expect(post).toHaveBeenCalledTimes(1);
});
it("terminal unknown status only GETs and has no paid write", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValue({
    data: { ...readJob, state: "unknown", poll_after_ms: null },
  });
  const post = vi.spyOn(api, "post");
  const env = setup();
  const hook = renderHook(() => useReceiptReadJob("bill", "job"), env);
  await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
  await act(async () => {
    await hook.result.current.refetch();
  });
  expect(get).toHaveBeenCalledTimes(2);
  expect(post).not.toHaveBeenCalled();
});
it("import invalidates receipt evidence but never the ledger", async () => {
  vi.spyOn(api, "post").mockResolvedValue({ data: {} });
  const env = setup();
  const invalidate = vi.spyOn(env.client, "invalidateQueries");
  const hook = renderHook(() => useImportReceiptRead(), env);
  await act(async () => {
    await hook.result.current.mutateAsync({
      session: 55,
      billId: "bill",
      key: "k",
      body: { confirmed_replace: true },
    });
  });
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["finance", "receipt-items", 55, "bill"],
  });
  expect(invalidate).not.toHaveBeenCalledWith({
    queryKey: ["finance", "transactions"],
  });
});
it("a late import response is rejected after session replacement", async () => {
  let resolve!: (v: unknown) => void;
  vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const env = setup();
  const invalidate = vi.spyOn(env.client, "invalidateQueries");
  const hook = renderHook(() => useImportReceiptRead(), env);
  let pending!: Promise<unknown>;
  act(() => {
    pending = hook.result.current
      .mutateAsync({ session: 55, billId: "bill", key: "k", body: {} })
      .catch((e) => e);
  });
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
  useAuthStore.setState({ sessionVersion: 56 });
  await act(async () => {
    resolve({ data: {} });
    expect(await pending).toMatchObject({ message: "session_changed" });
  });
  expect(invalidate).not.toHaveBeenCalled();
});
