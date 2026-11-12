import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { useUpdateTransactionAnnotations } from "./transactionAnnotations";

afterEach(() => vi.restoreAllMocks());
const payload = {
  id: "txn",
  key: "same-intent",
  display_description: "My title",
  note: "Note",
  tags: ["Remont"],
  project_id: null,
  expected_version: 0,
  expected_context_snapshot: "a".repeat(64),
};

it("uses only annotation fields and invalidates reads without installing a historical replay", async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const install = vi.spyOn(client, "setQueryData");
  const put = vi.spyOn(api, "put").mockResolvedValue({ data: { version: 1 } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useUpdateTransactionAnnotations(), {
    wrapper,
  });
  await act(async () => {
    await result.current.mutateAsync(payload);
  });
  const body = {
    display_description: "My title",
    note: "Note",
    tags: ["Remont"],
    project_id: null,
    expected_version: 0,
    expected_context_snapshot: "a".repeat(64),
  };
  expect(put).toHaveBeenCalledWith(
    "/finance/transactions/txn/annotations",
    body,
    { headers: { "Idempotency-Key": "same-intent" } },
  );
  expect(invalidate).toHaveBeenCalled();
  expect(install).not.toHaveBeenCalled();
  client.clear();
});

it("ignores a late save after the session changes", async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  let finish!: (value: unknown) => void;
  vi.spyOn(api, "put").mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useUpdateTransactionAnnotations(), {
    wrapper,
  });
  let pending!: Promise<unknown>;
  await act(async () => {
    pending = result.current.mutateAsync(payload);
  });
  act(() =>
    useAuthStore.setState((state) => ({
      sessionVersion: state.sessionVersion + 1,
    })),
  );
  await act(async () => {
    finish({ data: { version: 1 } });
    await pending;
  });
  expect(invalidate).not.toHaveBeenCalled();
  client.clear();
});
