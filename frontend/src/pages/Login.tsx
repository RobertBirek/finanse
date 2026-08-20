import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useLogin } from "../api/auth";
import { useAuthStore } from "../stores/authStore";

function getSafeReturnTo(returnTo: string | null): string {
  if (
    !returnTo ||
    !/^\/(?!\/)/.test(returnTo) ||
    returnTo.includes("\\") ||
    returnTo.split(/[?#]/)[0] === "/login"
  ) {
    return "/today";
  }

  return returnTo;
}

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const loginMutation = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const submitted = useRef(false);
  const loginError = loginMutation.error as {
    response?: { data?: { detail?: string } };
  } | null;
  const returnTo = new URLSearchParams(location.search).get("returnTo");
  const destination = getSafeReturnTo(returnTo);

  useEffect(() => {
    if (!submitted.current && !isLoading && isAuthenticated) {
      navigate(destination, { replace: true });
    }
  }, [destination, isAuthenticated, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="w-6 h-6 border-2 border-advisor-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    submitted.current = true;
    loginMutation.mutate(
      { email, password },
      { onSuccess: () => navigate(destination, { replace: true }) },
    );
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-advisor-500 flex items-center justify-center mx-auto mb-4">
            <span className="text-2xl font-bold text-white">A</span>
          </div>
          <h1 className="text-2xl font-bold text-white">Personal Advisor</h1>
          <p className="text-gray-400 mt-2">Zaloguj się, aby kontynuować</p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
            {loginMutation.isError && (
              <div className="bg-red-900/30 border border-red-800 text-red-400 px-4 py-3 rounded-lg text-sm">
                {loginError?.response?.data?.detail ||
                  "Nieprawidłowy email lub hasło"}
              </div>
            )}

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-300 mb-1.5"
              >
                Email
              </label>
              <input
                type="email"
                id="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="twoj@email.com"
                className="input"
                required
                autoFocus
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-300 mb-1.5"
              >
                Hasło
              </label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Wprowadź hasło"
                className="input"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="btn-primary w-full mt-2"
            >
              {loginMutation.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Logowanie...
                </span>
              ) : (
                "Zaloguj się"
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
