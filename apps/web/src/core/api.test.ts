import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
afterEach(() => vi.unstubAllGlobals());
it("unwraps data without exposing the envelope", async () => {
  const fetcher = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ data: { value: 3 } }),
  });
  vi.stubGlobal("fetch", fetcher);
  expect(await api("/api/v1/home")).toEqual({ value: 3 });
  expect(fetcher.mock.calls[0][1]).toMatchObject({
    credentials: "same-origin",
    cache: "no-store",
  });
});
it("preserves authentication errors for the protected shell", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({
        error: { code: "UNAUTHENTICATED", message: "로그인 필요" },
      }),
    }),
  );
  await expect(api("/api/v1/session")).rejects.toEqual(
    new ApiError(401, "UNAUTHENTICATED", "로그인 필요"),
  );
});
