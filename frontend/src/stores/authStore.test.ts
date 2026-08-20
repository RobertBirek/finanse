import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("../lib/api", () => ({
  default: { get, post: vi.fn() },
}));

import { useAuthStore } from "./authStore";

const user = {
  id: "user-1",
  email: "anna@example.com",
  display_name: "Anna",
  is_active: true,
};

afterEach(() => {
  get.mockReset();
  localStorage.clear();
  useAuthStore.setState({
    user: null,
    authStatus: "loading",
    isAuthenticated: false,
    isLoading: true,
  });
});

describe("authStore", () => {
  it("marks the session unavailable after a server error without clearing a known user", async () => {
    useAuthStore.setState({ user, isAuthenticated: true, isLoading: false });
    get.mockRejectedValue({ response: { status: 500 } });

    await useAuthStore.getState().fetchUser();

    expect(useAuthStore.getState()).toMatchObject({
      user,
      authStatus: "unavailable",
      isAuthenticated: true,
      isLoading: false,
    });
  });

  it("marks the session unavailable after a network timeout without storing a token", async () => {
    get.mockRejectedValue(new AxiosError("timeout", "ECONNABORTED"));

    await useAuthStore.getState().fetchUser();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      authStatus: "unavailable",
      isAuthenticated: false,
      isLoading: false,
    });
    expect(localStorage).not.toHaveProperty("token");
    expect(Object.keys(localStorage)).not.toContain("token");
    expect(useAuthStore.getState()).not.toHaveProperty("token");
  });

  it("marks a 401 response as unauthenticated", async () => {
    get.mockRejectedValue({ response: { status: 401 } });

    await useAuthStore.getState().fetchUser();

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      authStatus: "unauthenticated",
      isAuthenticated: false,
      isLoading: false,
    });
  });
});
