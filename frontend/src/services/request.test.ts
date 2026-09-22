import { describe, expect, it, vi } from "vitest";

describe("API request deduplication", () => {
  it("shares concurrent identical GET requests and evicts completed entries", async () => {
    vi.resetModules();
    let resolveFetch: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { request } = await import("./api");

    const first = request<{ ok: boolean }>("/deduplicated", { auth: false });
    const second = request<{ ok: boolean }>("/deduplicated", { auth: false });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFetch?.(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(Promise.all([first, second])).resolves.toEqual([
      { ok: true },
      { ok: true },
    ]);

    vi.mocked(fetchMock).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      request<{ ok: boolean }>("/deduplicated", { auth: false }),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
