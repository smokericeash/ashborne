import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthContext } from "../../context/useAuth";
import { administrator, authValue, operator, viewer } from "../../test/render";
import type { User } from "../../types";
import { ProtectedRoute } from "./ProtectedRoute";

function renderRoute(path: string, user: User | null) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthContext.Provider value={authValue(user)}>
        <Routes>
          <Route path="/login" element={<div>Login screen</div>} />
          <Route path="/unauthorized" element={<div>Permission denied</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/dashboard" element={<div>Dashboard content</div>} />
            <Route
              path="/settings"
              element={
                <ProtectedRoute roles={["ADMINISTRATOR"]}>
                  <div>Settings content</div>
                </ProtectedRoute>
              }
            />
          </Route>
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects unauthenticated users to login", async () => {
    renderRoute("/dashboard", null);
    expect(await screen.findByText("Login screen")).toBeInTheDocument();
  });

  it("allows an authenticated user through a general protected route", async () => {
    renderRoute("/dashboard", operator);
    expect(await screen.findByText("Dashboard content")).toBeInTheDocument();
  });

  it("denies a viewer an administrator route", async () => {
    renderRoute("/settings", viewer);
    expect(await screen.findByText("Permission denied")).toBeInTheDocument();
  });

  it("allows an administrator through an administrator route", async () => {
    renderRoute("/settings", administrator);
    expect(await screen.findByText("Settings content")).toBeInTheDocument();
  });
});
