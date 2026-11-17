import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import { useBill, useBills } from "./bills";
import { useCategories } from "./finance";

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null });
});
it("does not show cached bill or taxonomy from a previous owner", async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  useAuthStore.setState({
    user: {
      id: "owner-a",
      email: "a@test",
      display_name: "A",
      is_active: true,
    },
  });
  const get = vi
    .spyOn(api, "get")
    .mockResolvedValue({ data: { marker: "private-a" } });
  const { result, unmount } = renderHook(
    () => ({
      bill: useBill("bill-a"),
      bills: useBills(),
      categories: useCategories(),
    }),
    { wrapper },
  );
  await waitFor(() => expect(result.current.bill.data).toBeTruthy());
  get.mockImplementation(() => new Promise(() => {}));
  act(() =>
    useAuthStore.setState({
      user: {
        id: "owner-b",
        email: "b@test",
        display_name: "B",
        is_active: true,
      },
    }),
  );
  expect(result.current.bill.data).toBeUndefined();
  expect(result.current.bills.data).toBeUndefined();
  expect(result.current.categories.data).toBeUndefined();
  unmount();
  client.clear();
});
