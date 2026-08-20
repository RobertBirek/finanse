import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Login } from "./Login";

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));
const authState = vi.hoisted(() => ({
  value: { isAuthenticated: false, isLoading: false },
}));

vi.mock("../api/auth", () => ({
  useLogin: () => ({ mutate, error: null, isError: false, isPending: false }),
}));

vi.mock("../stores/authStore", () => ({
  useAuthStore: (selector: (state: typeof authState.value) => unknown) =>
    selector(authState.value),
}));

function Destination() {
  const location = useLocation();
  return <p>{`${location.pathname}${location.search}${location.hash}`}</p>;
}

function renderLogin(returnTo: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`/login?returnTo=${encodeURIComponent(returnTo)}`]}
      >
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Destination />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function submitLogin() {
  fireEvent.change(screen.getByPlaceholderText("twoj@email.com"), {
    target: { value: "anna@example.com" },
  });
  fireEvent.change(screen.getByPlaceholderText("Wprowadź hasło"), {
    target: { value: "password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));
}

afterEach(() => {
  mutate.mockReset();
  authState.value = { isAuthenticated: false, isLoading: false };
});

describe("Login", () => {
  it("returns to a valid local route after successful login", async () => {
    mutate.mockImplementation((_values, options) => {
      options.onSuccess();
    });
    renderLogin("/finances/reports?month=8#budget");

    submitLogin();

    await waitFor(() => {
      expect(
        screen.getByText("/finances/reports?month=8#budget"),
      ).toBeInTheDocument();
    });
  });

  it.each(["//evil.example", "/\\evil", "https://evil"])(
    "falls back to today for invalid returnTo %s",
    async (returnTo) => {
      mutate.mockImplementation((_values, options) => {
        options.onSuccess();
      });
      renderLogin(returnTo);

      submitLogin();

      await waitFor(() => {
        expect(screen.getByText("/today")).toBeInTheDocument();
      });
    },
  );

  it("falls back to today instead of returning to login after successful login", async () => {
    mutate.mockImplementation((_values, options) => {
      options.onSuccess();
    });
    renderLogin("/login");

    submitLogin();

    await waitFor(() => {
      expect(screen.getByText("/today")).toBeInTheDocument();
    });
  });
});
