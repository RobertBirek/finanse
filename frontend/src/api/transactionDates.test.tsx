import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { useUpdateTransactionDates } from "./finance";

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
it("does not invalidate the next session's finance cache after a delayed date reply", async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const owner = {
    id: "a",
    email: "a@example.test",
    display_name: "A",
    is_active: true,
  };
  useAuthStore.setState({ user: owner });
  let resolve!: (data: unknown) => void;
  vi.spyOn(api, "patch").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useUpdateTransactionDates(), { wrapper });
  let pending!: Promise<unknown>;
  await act(async () => {
    pending = result.current.mutateAsync({
      id: "txn",
      booking_date: "2026-02-02",
      purchase_date: "2026-01-30",
      expected_version: 0,
      expected_updated_at: "2026-11-03T12:00:00Z",
    });
  });
  act(() => {
    useAuthStore.setState((state) => ({
      user: { ...owner },
      sessionVersion: state.sessionVersion + 2,
    }));
  });
  await act(async () => {
    resolve({ data: { id: "txn" } });
    await pending;
  });
  expect(invalidate).not.toHaveBeenCalled();
  client.clear();
});
