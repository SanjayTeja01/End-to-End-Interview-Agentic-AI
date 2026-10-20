import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getAccessToken, setAccessToken } from "@/lib/api";

describe("api client", () => {
  afterEach(() => { vi.restoreAllMocks(); setAccessToken(null); });

  it("sends the in-memory bearer token", async () => {
    setAccessToken("abc");
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    await api("/x");
    const headers = f.mock.calls[0][1]!.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer abc");
  });

  it("refreshes once on 401 and retries", async () => {
    setAccessToken("old");
    const f = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(api("/thing")).resolves.toEqual({ ok: true });
    expect(getAccessToken()).toBe("new");
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("raises structured errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "forbidden", message: "No" } }), { status: 403 }));
    await expect(api("/y")).rejects.toBeInstanceOf(ApiError);
  });
});
