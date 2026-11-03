import { create } from "zustand";
import api, { resetUnauthorizedRedirect } from "../lib/api";

interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

type AuthStatus =
  "loading" | "authenticated" | "unauthenticated" | "unavailable";
let authRequestVersion = 0;

function startAuthRequest(): number {
  authRequestVersion += 1;
  return authRequestVersion;
}

function isCurrentAuthRequest(requestVersion: number): boolean {
  return requestVersion === authRequestVersion;
}

function getResponseStatus(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("response" in error)) {
    return undefined;
  }

  const response = error.response;
  if (
    typeof response !== "object" ||
    response === null ||
    !("status" in response)
  ) {
    return undefined;
  }

  return typeof response.status === "number" ? response.status : undefined;
}

interface AuthState {
  /** Changes on login/logout or owner change, not a same-session /auth/me refresh. */
  sessionVersion: number;
  user: User | null;
  authStatus: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  retryFetchUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  sessionVersion: 0,
  user: null,
  authStatus: "loading",
  isAuthenticated: false,
  isLoading: true,

  login: async (email: string, password: string) => {
    const requestVersion = startAuthRequest();
    await api.post("/auth/login", { email, password });
    if (!isCurrentAuthRequest(requestVersion)) return;

    const { data } = await api.get<User>("/auth/me");
    if (!isCurrentAuthRequest(requestVersion)) return;

    resetUnauthorizedRedirect();
    set((state) => ({
      sessionVersion: state.sessionVersion + 1,
      user: data,
      authStatus: "authenticated",
      isAuthenticated: true,
      isLoading: false,
    }));
  },

  logout: async () => {
    const requestVersion = startAuthRequest();
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore
    }
    if (!isCurrentAuthRequest(requestVersion)) return;

    set((state) => ({
      sessionVersion: state.sessionVersion + 1,
      user: null,
      authStatus: "unauthenticated",
      isAuthenticated: false,
      isLoading: false,
    }));
  },

  fetchUser: async () => {
    const requestVersion = startAuthRequest();
    try {
      const { data } = await api.get<User>("/auth/me");
      if (!isCurrentAuthRequest(requestVersion)) return;

      set((state) => ({
        sessionVersion:
          state.sessionVersion + (state.user?.id !== data.id ? 1 : 0),
        user: data,
        authStatus: "authenticated",
        isAuthenticated: true,
        isLoading: false,
      }));
    } catch (error) {
      if (!isCurrentAuthRequest(requestVersion)) return;

      if (getResponseStatus(error) === 401) {
        set((state) => ({
          sessionVersion: state.sessionVersion + (state.user !== null ? 1 : 0),
          user: null,
          authStatus: "unauthenticated",
          isAuthenticated: false,
          isLoading: false,
        }));
        return;
      }

      set((state) => ({
        authStatus: "unavailable",
        isAuthenticated: state.user !== null,
        isLoading: false,
      }));
    }
  },

  retryFetchUser: async () => {
    await useAuthStore.getState().fetchUser();
  },
}));
