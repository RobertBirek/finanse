import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "./ProtectedRoute";

const authState = vi.hoisted(() => ({
  value: {
    authStatus: "unauthenticated",
    isLoading: false,
    retryFetchUser: vi.fn(),
  },
}));

vi.mock("../stores/authStore", () => ({
  useAuthStore: () => authState.value,
}));

function Location() {
  const location = useLocation();
  return <p>{`${location.pathname}${location.search}${location.hash}`}</p>;
}

function renderRoute(initialEntry = "/finances/reports?month=8#budget") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/login" element={<Location />} />
        <Route
          path="*"
          element={
            <ProtectedRoute>
              <p>Protected content</p>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  authState.value = {
    authStatus: "unauthenticated",
    isLoading: false,
    retryFetchUser: vi.fn(),
  };
});

describe("ProtectedRoute", () => {
  it("redirects an unauthenticated user with the complete local return route", () => {
    renderRoute();

    expect(
      screen.getByText(
        "/login?returnTo=%2Ffinances%2Freports%3Fmonth%3D8%23budget",
      ),
    ).toBeInTheDocument();
  });

  it("shows an accessible retry screen instead of redirecting when authentication is unavailable", () => {
    const retryFetchUser = vi.fn();
    authState.value = {
      authStatus: "unavailable",
      isLoading: false,
      retryFetchUser,
    };

    renderRoute();

    expect(
      screen.getByRole("heading", { name: /nie można połączyć/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^\/login/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /spróbuj ponownie/i }));
    expect(retryFetchUser).toHaveBeenCalledOnce();
  });
});
