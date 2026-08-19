import { AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import api from "./api";

const requestInterceptor = api.interceptors.request.handlers?.[0]?.fulfilled;

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
