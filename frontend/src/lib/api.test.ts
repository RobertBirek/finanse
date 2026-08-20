import { AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "./api";

const requestInterceptor = api.interceptors.request.handlers?.[0]?.fulfilled;
const responseErrorInterceptor =
  api.interceptors.response.handlers?.[0]?.rejected;

async function applyRequestInterceptor(method: string) {
  if (!requestInterceptor) {
    throw new Error("CSRF request interceptor is not registered");
  }
  return requestInterceptor({
    headers: new AxiosHeaders(),
    method,
  } as InternalAxiosRequestConfig);
}

afterEach(() => {
  document.cookie = "advisor_csrf=; Max-Age=0; path=/";
  document.cookie = "not_advisor_csrf=; Max-Age=0; path=/";
});

describe("CSRF request interceptor", () => {
  it("does not set a CSRF header for GET requests", async () => {
    document.cookie = "advisor_csrf=csrf-token; path=/";

    const config = await applyRequestInterceptor("get");

    expect(config.headers.get("X-CSRF-Token")).toBeUndefined();
  });

  it("sets a CSRF header for unsafe requests from the exact cookie name", async () => {
    document.cookie = "not_advisor_csrf=wrong; path=/";
    document.cookie = "advisor_csrf=csrf-token; path=/";

    const config = await applyRequestInterceptor("post");

    expect(config.headers.get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("does not set a CSRF header when the cookie is missing", async () => {
    const config = await applyRequestInterceptor("delete");

    expect(config.headers.get("X-CSRF-Token")).toBeUndefined();
  });
});

describe("authentication response interceptor", () => {
  it("redirects a 401 to login with the encoded current local route", async () => {
    const originalLocation = window.location;
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        pathname: "/finances/reports",
        search: "?month=8",
        hash: "#budget",
        assign,
      },
    });

    try {
      await expect(
        responseErrorInterceptor?.({ response: { status: 401 } }),
      ).rejects.toEqual({ response: { status: 401 } });
      expect(assign).toHaveBeenCalledWith(
        "/login?returnTo=%2Ffinances%2Freports%3Fmonth%3D8%23budget",
      );
    } finally {
      Object.defineProperty(window, "location", {
        configurable: true,
        value: originalLocation,
      });
    }
  });

  it.each([403, 429, 500])(
    "does not redirect a %i response",
    async (status) => {
      const originalLocation = window.location;
      const assign = vi.fn();
      Object.defineProperty(window, "location", {
        configurable: true,
        value: { pathname: "/finances", search: "", hash: "", assign },
      });

      try {
        await expect(
          responseErrorInterceptor?.({ response: { status } }),
        ).rejects.toEqual({ response: { status } });
        expect(assign).not.toHaveBeenCalled();
      } finally {
        Object.defineProperty(window, "location", {
          configurable: true,
          value: originalLocation,
        });
      }
    },
  );
});
