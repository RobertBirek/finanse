import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

const unsafeMethods = new Set(["post", "patch", "put", "delete"]);

function getCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(prefix))
    ?.slice(prefix.length);
}

api.interceptors.request.use((config) => {
  if (!unsafeMethods.has(config.method?.toLowerCase() ?? "")) {
    return config;
  }

  const csrfToken = getCookie("advisor_csrf");
  if (csrfToken) {
    config.headers.set("X-CSRF-Token", csrfToken);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const isLoginPage = window.location.pathname === "/login";
      if (!isLoginPage) {
        const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        window.location.assign(
          `/login?returnTo=${encodeURIComponent(returnTo)}`,
        );
      }
    }
    return Promise.reject(error);
  },
);

export default api;
