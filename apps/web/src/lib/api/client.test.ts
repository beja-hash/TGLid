import { afterEach, describe, expect, it, vi } from "vitest";

import {
  apiRequest,
  ApiError,
  readCsrfToken,
  setUnauthorizedHandler,
} from "./client";

const originalFetch = globalThis.fetch;
function mockResponse(
  body: unknown,
  status = 200,
  headers?: HeadersInit,
): Response {
  return new Response(body === undefined ? undefined : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

afterEach(() => {
  globalThis.fetch = originalFetch;
  document.cookie = "tglid_csrf=; Max-Age=0; path=/";
  setUnauthorizedHandler(undefined);
});

describe("api client", () => {
  it("reads only the CSRF cookie", () => {
    expect(readCsrfToken("tglid_session=secret; tglid_csrf=csrf-value")).toBe(
      "csrf-value",
    );
  });

  it("sends JSON, credentials and CSRF for changes", async () => {
    document.cookie = "tglid_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(mockResponse({ id: "1" }));
    globalThis.fetch = fetchMock;
    await apiRequest<{ id: string }>("/api/v1/users", {
      method: "POST",
      body: { full_name: "Test" },
    });
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(init?.body).toBe(JSON.stringify({ full_name: "Test" }));
  });

  it("does not require CSRF for GET", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(mockResponse({ id: "1" }));
    globalThis.fetch = fetchMock;
    await apiRequest<{ id: string }>("/api/v1/auth/me");
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
  });

  it("returns structured retry information", async () => {
    globalThis.fetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        mockResponse(
          { error: { code: "RATE_LIMITED", message: "Too many" } },
          429,
          { "Retry-After": "30" },
        ),
      );
    await expect(
      apiRequest("/api/v1/auth/login", { method: "POST", body: {} }),
    ).rejects.toMatchObject({
      status: 429,
      code: "RATE_LIMITED",
      retryAfter: 30,
    });
  });

  it("clears auth state through the centralized 401 handler", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    globalThis.fetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        mockResponse(
          { error: { code: "UNAUTHORIZED", message: "Expired" } },
          401,
        ),
      );
    await expect(apiRequest("/api/v1/auth/me")).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(handler).toHaveBeenCalledOnce();
  });

  it("handles empty logout responses", async () => {
    document.cookie = "tglid_csrf=csrf-value; path=/";
    globalThis.fetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 204 }));
    await expect(
      apiRequest<void>("/api/v1/auth/logout", { method: "POST" }),
    ).resolves.toBeUndefined();
  });
});
