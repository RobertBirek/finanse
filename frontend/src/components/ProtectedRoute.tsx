import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

interface Props {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: Props) {
  const { authStatus, isLoading, retryFetchUser } = useAuthStore();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-950">
        <div className="w-8 h-8 border-2 border-advisor-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (authStatus === "unavailable") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-950 p-4">
        <section className="card max-w-md text-center" aria-live="polite">
          <h1 className="text-xl font-semibold text-white">
            Nie można połączyć z serwerem
          </h1>
          <p className="mt-2 text-gray-400">
            Sprawdź połączenie z internetem i spróbuj ponownie.
          </p>
          <button
            className="btn-primary mt-6"
            type="button"
            onClick={() => void retryFetchUser()}
          >
            Spróbuj ponownie
          </button>
        </section>
      </main>
    );
  }

  if (authStatus === "unauthenticated") {
    const returnTo = `${location.pathname}${location.search}${location.hash}`;
    return (
      <Navigate
        to={`/login?returnTo=${encodeURIComponent(returnTo)}`}
        replace
      />
    );
  }

  return <>{children}</>;
}
