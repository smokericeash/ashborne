import { beforeEach, describe, expect, it, vi } from "vitest";

describe("access-token refresh", () => {
  beforeEach(() => {
    vi.resetModules();
    sessionStorage.setItem("kandor.refresh_token", "refresh-before-reload");
    sessionStorage.setItem(
      "kandor.access_token",
      "legacy-access-must-not-load",
    );
  });

  it("restores a tab using the refresh token and retries with a rotated memory-only access token", async () => {
    const refreshedUser = {
      id: "22222222-2222-4222-8222-222222222222",
      email: "operator@example.local",
      display_name: "Operator",
      role: "VIEWER",
      is_active: true,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      last_login_at: null,
    } as const;
    const fetchMock = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/auth/refresh")) {
          expect(JSON.parse(String(init?.body))).toEqual({
            refresh_token: "refresh-before-reload",
          });
          return new Response(
            JSON.stringify({
              access_token: "access-after-refresh",
              refresh_token: "refresh-after-refresh",
              token_type: "bearer",
              expires_in: 900,
              user: refreshedUser,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        const authorization = new Headers(init?.headers).get("Authorization");
        if (!authorization) {
          return new Response(JSON.stringify({ detail: "not authenticated" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          });
        }
        expect(authorization).toBe("Bearer access-after-refresh");
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    const { onSessionUpdated, request } = await import("./api");
    const { tokenStore } = await import("./tokenStore");
    const sessionUpdated = vi.fn();
    onSessionUpdated(sessionUpdated);
    await expect(request<{ ok: boolean }>("/protected")).resolves.toEqual({
      ok: true,
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.getAccess()).toBe("access-after-refresh");
    expect(sessionStorage.getItem("kandor.refresh_token")).toBe(
      "refresh-after-refresh",
    );
    expect(sessionStorage.getItem("kandor.access_token")).toBeNull();
    expect(sessionUpdated).toHaveBeenCalledWith(refreshedUser);
    onSessionUpdated(null);
  });
});
