import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

const { get, post, resetUnauthorizedRedirect } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  resetUnauthorizedRedirect: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: { get, post },
  resetUnauthorizedRedirect,
}));

import { useAuthStore } from "./authStore";

const user = {
  id: "user-1",
  email: "anna@example.com",
  display_name: "Anna",
  is_active: true,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

afterEach(() => {
  get.mockReset();
  post.mockReset();
  resetUnauthorizedRedirect.mockReset();
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

  it("does not let a stale fetch 401 overwrite a newer successful login", async () => {
    const staleFetch = deferred<{ data: typeof user }>();
    get
      .mockImplementationOnce(() => staleFetch.promise)
      .mockResolvedValueOnce({ data: user });
    post.mockResolvedValue({ status: 204 });

    const fetchPromise = useAuthStore.getState().fetchUser();
    await useAuthStore.getState().login("anna@example.com", "password");
    staleFetch.reject({ response: { status: 401 } });
    await fetchPromise;

    expect(useAuthStore.getState()).toMatchObject({
      user,
      authStatus: "authenticated",
      isAuthenticated: true,
    });
  });

  it("does not let a stale fetch success reauthenticate after logout", async () => {
    const staleFetch = deferred<{ data: typeof user }>();
    get.mockImplementationOnce(() => staleFetch.promise);
    post.mockResolvedValue({ status: 204 });

    const fetchPromise = useAuthStore.getState().fetchUser();
    await useAuthStore.getState().logout();
    staleFetch.resolve({ data: user });
    await fetchPromise;

    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      authStatus: "unauthenticated",
      isAuthenticated: false,
    });
  });
});
