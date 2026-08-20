import { create } from "zustand";
import api from "../lib/api";

interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

type AuthStatus =
  "loading" | "authenticated" | "unauthenticated" | "unavailable";

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
  user: null,
  authStatus: "loading",
  isAuthenticated: false,
  isLoading: true,

  login: async (email: string, password: string) => {
    await api.post("/auth/login", { email, password });
    const { data } = await api.get<User>("/auth/me");
    set({
      user: data,
      authStatus: "authenticated",
      isAuthenticated: true,
      isLoading: false,
    });
  },

  logout: async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore
    }
    set({
      user: null,
      authStatus: "unauthenticated",
      isAuthenticated: false,
      isLoading: false,
    });
  },

  fetchUser: async () => {
    try {
      const { data } = await api.get<User>("/auth/me");
      set({
        user: data,
        authStatus: "authenticated",
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error) {
      if (getResponseStatus(error) === 401) {
        set({
          user: null,
          authStatus: "unauthenticated",
          isAuthenticated: false,
          isLoading: false,
        });
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
