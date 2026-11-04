import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import {
  useSaveReceiptDraft,
  useApplyReceiptPayment,
  useReceiptStores,
  useReceiptHistory,
} from "./receiptItems";
import { body } from "../components/finance/receipts/receiptTestData";
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
it("does not send client session/key metadata, never auto retries, and refuses a replaced session", async () => {
  const post = vi.spyOn(api, "post").mockRejectedValue(new Error("Lost"));
  const env = setup();
  const invalidate = vi.spyOn(env.client, "invalidateQueries");
  const hook = renderHook(() => useSaveReceiptDraft(), env);
  const input = {
    session: 55,
    billId: "bill",
    key: "stable",
    body: { expected_version: 0, expected_bill_version: 1, body },
  };
  await act(async () => {
    await expect(hook.result.current.mutateAsync(input)).rejects.toThrow(
      "Lost",
    );
  });
  expect(post).toHaveBeenCalledExactlyOnceWith(
    "/finance/bills/bill/items/draft",
    input.body,
    { headers: { "Idempotency-Key": "stable" } },
  );
  expect(invalidate).not.toHaveBeenCalledWith({
    queryKey: ["finance", "transactions"],
  });
  useAuthStore.setState({ sessionVersion: 56 });
  await act(async () => {
    await expect(hook.result.current.mutateAsync(input)).rejects.toThrow(
      "session_changed",
    );
  });
  expect(post).toHaveBeenCalledTimes(1);
});
it("late responses from a replaced session do not invalidate the replacement cache", async () => {
  let resolve!: (value: unknown) => void;
  vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const env = setup(),
    invalidate = vi.spyOn(env.client, "invalidateQueries"),
    hook = renderHook(() => useApplyReceiptPayment(), env);
  let promise: Promise<unknown>;
  act(() => {
    promise = hook.result.current.mutateAsync({
      session: 55,
      billId: "bill",
      key: "k",
      body: { confirmed: true },
    });
  });
  await waitFor(() => expect(api.post).toHaveBeenCalledOnce());
  useAuthStore.setState({ sessionVersion: 56 });
  await act(async () => {
    resolve({ data: {} });
    await promise;
  });
  expect(invalidate).not.toHaveBeenCalled();
});
it("paging stores can enumerate past the first page and history is never triggered on mount", async () => {
  const get = vi.spyOn(api, "get").mockImplementation(async (_url, config) => ({
    data: (config?.params as { cursor?: string } | undefined)?.cursor
      ? { items: [{ id: "b", name: "B" }], next_cursor: null }
      : { items: [{ id: "a", name: "A" }], next_cursor: "next" },
  }));
  const env = setup(),
    hook = renderHook(() => {
      const stores = useReceiptStores();
      return { stores, storeData: stores.data, history: useReceiptHistory() };
    }, env);
  await waitFor(() => expect(hook.result.current.stores.isSuccess).toBe(true));
  await act(async () => {
    await hook.result.current.stores.fetchNextPage();
  });
  expect(get.mock.calls.map((c) => c[1]?.params)).toEqual([
    { cursor: undefined, include_inactive: false },
    { cursor: "next", include_inactive: false },
  ]);
  expect(hook.result.current.stores.error).toBeNull();
  expect(
    env.client.getQueryData(["finance", "receipt-stores", 55, null, false]),
  ).toMatchObject({
    pages: [{ items: [{ id: "a" }] }, { items: [{ id: "b" }] }],
  });
  await waitFor(() =>
    expect(
      hook.result.current.stores.data?.pages.flatMap((p) =>
        p.items.map((s) => s.id),
      ),
    ).toEqual(["a", "b"]),
  );
  expect(get).toHaveBeenCalledTimes(2);
});
