import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthContext, type AuthContextValue } from "../context/useAuth";
import {
  AgentsRevisionContext,
  AuditRevisionContext,
  DashboardRevisionContext,
  LiveConnectionContext,
  LiveContext,
  TasksRevisionContext,
} from "../context/useLive";
import { HostSelectionProvider } from "../context/HostSelectionContext";
import { ToastContext } from "../context/useToast";
import type { User } from "../types";

export const administrator: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@example.local",
  display_name: "ASHBORNE Administrator",
  role: "ADMINISTRATOR",
  is_active: true,
  created_at: "2026-09-01T00:00:00Z",
  last_login_at: "2026-09-14T00:00:00Z",
};

export const operator: User = {
  ...administrator,
  id: "22222222-2222-4222-8222-222222222222",
  email: "operator@example.local",
  display_name: "ASHBORNE Operator",
  role: "OPERATOR",
};

export const viewer: User = {
  ...administrator,
  id: "33333333-3333-4333-8333-333333333333",
  email: "viewer@example.local",
  display_name: "ASHBORNE Viewer",
  role: "VIEWER",
};

export function authValue(
  user: User | null,
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    user,
    loading: false,
    isAuthenticated: Boolean(user),
    login: vi.fn(),
    logout: vi.fn(),
    hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
    ...overrides,
  };
}

interface ContextOptions extends Omit<RenderOptions, "wrapper"> {
  user?: User | null;
  auth?: AuthContextValue;
  route?: string;
  connected?: boolean;
}

export function renderWithContexts(
  ui: ReactElement,
  options: ContextOptions = {},
) {
  const {
    user = administrator,
    auth = authValue(user),
    route = "/",
    connected = true,
    ...renderOptions
  } = options;
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthContext.Provider value={auth}>
        <LiveConnectionContext.Provider value={connected}>
          <AgentsRevisionContext.Provider value={0}>
            <TasksRevisionContext.Provider value={0}>
              <AuditRevisionContext.Provider value={0}>
                <DashboardRevisionContext.Provider value={0}>
                  <LiveContext.Provider
                    value={{
                      connected,
                      lastEvent: null,
                      revision: 0,
                      agentsRevision: 0,
                      tasksRevision: 0,
                      auditRevision: 0,
                      dashboardRevision: 0,
                    }}
                  >
                    <ToastContext.Provider value={{ notify: vi.fn() }}>
                      <HostSelectionProvider>{ui}</HostSelectionProvider>
                    </ToastContext.Provider>
                  </LiveContext.Provider>
                </DashboardRevisionContext.Provider>
              </AuditRevisionContext.Provider>
            </TasksRevisionContext.Provider>
          </AgentsRevisionContext.Provider>
        </LiveConnectionContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
    renderOptions,
  );
}
