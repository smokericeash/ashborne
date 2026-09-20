import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "../pages/LoginPage";
import { tokenStore } from "../services/tokenStore";
import { AuthProvider } from "./AuthContext";
import { useAuth } from "./useAuth";

const authenticatedUser = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@example.local",
  display_name: "ASHBORNE Administrator",
  role: "ADMINISTRATOR" as const,
  is_active: true,
  created_at: "2026-09-01T00:00:00Z",
  last_login_at: "2026-09-14T00:00:00Z",
};

function Destination() {
  const { user } = useAuth();
  return <div>Welcome {user?.email}</div>;
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<Destination />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("authentication flow", () => {
  beforeEach(() => tokenStore.clear());

  it("normalizes the login email, keeps access in memory, and persists only refresh state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "access-one",
          refresh_token: "refresh-one",
          token_type: "bearer",
          expires_in: 900,
          user: authenticatedUser,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderLogin();

    await user.type(
      screen.getByLabelText("Email address"),
      "  Admin@Example.Local  ",
    );
    await user.type(screen.getByLabelText("Password"), "CorrectHorse123");
    await user.click(screen.getByRole("button", { name: "Authenticate" }));

    expect(
      await screen.findByText("Welcome admin@example.local"),
    ).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith("/api/v1/auth/login")).toBe(true);
    expect(JSON.parse(String(init.body))).toEqual({
      email: "admin@example.local",
      password: "CorrectHorse123",
    });
    expect(tokenStore.getAccess()).toBe("access-one");
    expect(sessionStorage.getItem("ashborne.refresh_token")).toBe(
      "refresh-one",
    );
    expect(sessionStorage.getItem("ashborne.access_token")).toBeNull();
  });

  it("shows a safe invalid-credentials message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "invalid email or password" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const user = userEvent.setup();
    renderLogin();

    await user.type(
      screen.getByLabelText("Email address"),
      "viewer@example.local",
    );
    await user.type(screen.getByLabelText("Password"), "IncorrectPass1");
    await user.click(screen.getByRole("button", { name: "Authenticate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The email or password is incorrect.",
    );
    expect(tokenStore.getAccess()).toBeNull();
  });
});
