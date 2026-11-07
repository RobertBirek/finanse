import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import api from "../lib/api";
import { useCreditCard, useCardMutation } from "./creditCards";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));
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
it("maps only a missing card to setup, not network or permission failures", async () => {
  vi.mocked(api.get).mockRejectedValueOnce({ response: { status: 404 } });
  const { wrapper } = setup();
  const { result } = renderHook(() => useCreditCard("card"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toBeNull();
  vi.mocked(api.get).mockRejectedValueOnce({ response: { status: 403 } });
  const next = renderHook(() => useCreditCard("other"), { wrapper });
  await waitFor(() => expect(next.result.current.isError).toBe(true));
});
it("invalidates dependent balances after a successful card booking", async () => {
  vi.mocked(api.post).mockResolvedValueOnce({ data: { id: "entry" } });
  const { client, wrapper } = setup();
  client.setQueryData(
    ["finance", "accounts"],
    [{ id: "card", balance_pln: 0 }],
  );
  const { result } = renderHook(() => useCardMutation("card", "/charges"), {
    wrapper,
  });
  await act(async () => {
    await result.current.mutateAsync({ amount_pln: 507 });
  });
  expect(client.getQueryState(["finance", "accounts"])?.isInvalidated).toBe(
    true,
  );
  expect(api.post).toHaveBeenCalledWith(
    "/finance/accounts/card/credit-card/charges",
    { amount_pln: 507 },
  );
});
