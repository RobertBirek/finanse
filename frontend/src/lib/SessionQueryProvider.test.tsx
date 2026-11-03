import { act, render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import api from "./api";
import { useAuthStore } from "../stores/authStore";
import { SessionQueryProvider } from "./SessionQueryProvider";

const owner = {
  id: "a",
  email: "a@example.test",
  display_name: "A",
  is_active: true,
};
beforeEach(() =>
  useAuthStore.setState({
    user: owner,
    isAuthenticated: true,
    authStatus: "authenticated",
  }),
);
afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null, isAuthenticated: false });
});
function PrivateView({ load }: { load: () => Promise<string> }) {
  const result = useQuery({
    queryKey: ["finance", "transactions"],
    queryFn: load,
    staleTime: Infinity,
  });
  return <p>{result.data ?? "Loading"}</p>;
}
it("does not show an old owner's cached ledger during the next owner's fetch", async () => {
  let resolve!: (value: string) => void;
  const load = vi
    .fn()
    .mockResolvedValueOnce("A private ledger")
    .mockImplementationOnce(
      () =>
        new Promise<string>((r) => {
          resolve = r;
        }),
    );
  render(
    <SessionQueryProvider>
      <PrivateView load={load} />
    </SessionQueryProvider>,
  );
  await screen.findByText("A private ledger");
  vi.spyOn(api, "post").mockResolvedValue({});
  vi.spyOn(api, "get").mockResolvedValue({ data: { ...owner, id: "b" } });
  await act(async () => {
    await useAuthStore.getState().logout();
    await useAuthStore.getState().login("b@example.test", "test");
  });
  expect(screen.queryByText("A private ledger")).not.toBeInTheDocument();
  expect(screen.getByText("Loading")).toBeInTheDocument();
  await act(async () => resolve("B private ledger"));
  await screen.findByText("B private ledger");
});
it("a late old-session query cannot populate a new login even for the same owner", async () => {
  let oldResolve!: (value: string) => void;
  const load = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<string>((r) => {
          oldResolve = r;
        }),
    )
    .mockResolvedValueOnce("Fresh login ledger");
  render(
    <SessionQueryProvider>
      <PrivateView load={load} />
    </SessionQueryProvider>,
  );
  await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  vi.spyOn(api, "post").mockResolvedValue({});
  vi.spyOn(api, "get").mockResolvedValue({ data: { ...owner } });
  await act(async () => {
    await useAuthStore.getState().logout();
    await useAuthStore.getState().login(owner.email, "test");
  });
  await screen.findByText("Fresh login ledger");
  await act(async () => oldResolve("Old login secret"));
  expect(screen.queryByText("Old login secret")).not.toBeInTheDocument();
});
it("same-session auth refresh retains cache instead of resetting the provider", async () => {
  const load = vi.fn().mockResolvedValue("Unchanged session ledger");
  render(
    <SessionQueryProvider>
      <PrivateView load={load} />
    </SessionQueryProvider>,
  );
  await screen.findByText("Unchanged session ledger");
  vi.spyOn(api, "get").mockResolvedValue({ data: { ...owner } });
  await act(async () => useAuthStore.getState().fetchUser());
  expect(screen.getByText("Unchanged session ledger")).toBeInTheDocument();
  expect(load).toHaveBeenCalledTimes(1);
});
