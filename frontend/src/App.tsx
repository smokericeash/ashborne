import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { AppShell } from "./components/layout/AppShell";
import { PageLoader } from "./components/ui";
import { HostSelectionProvider } from "./context/HostSelectionContext";
import { LiveProvider } from "./context/LiveContext";
import { LoginPage } from "./pages/LoginPage";

const lazyPage = <T extends Record<string, unknown>, K extends keyof T>(
  loader: () => Promise<T>,
  name: K,
) =>
  lazy(() =>
    loader().then((module) => ({
      default: module[name] as ComponentType,
    })),
  );

const AgentDetailPage = lazyPage(
  () => import("./pages/AgentDetailPage"),
  "AgentDetailPage",
);
const AgentsPage = lazyPage(() => import("./pages/AgentsPage"), "AgentsPage");
const AuditPage = lazyPage(() => import("./pages/AuditPage"), "AuditPage");
const BulkOperationPage = lazyPage(
  () => import("./pages/BulkOperationPage"),
  "BulkOperationPage",
);
const DashboardPage = lazyPage(
  () => import("./pages/DashboardPage"),
  "DashboardPage",
);
const OperatorConsolePage = lazyPage(
  () => import("./pages/OperatorConsolePage"),
  "OperatorConsolePage",
);
const SettingsPage = lazyPage(
  () => import("./pages/SettingsPage"),
  "SettingsPage",
);
const TasksPage = lazyPage(() => import("./pages/TasksPage"), "TasksPage");
const UsersPage = lazyPage(() => import("./pages/UsersPage"), "UsersPage");
const NotFoundPage = lazyPage(
  () => import("./pages/SystemPages"),
  "NotFoundPage",
);
const UnauthorizedPage = lazyPage(
  () => import("./pages/SystemPages"),
  "UnauthorizedPage",
);

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route
            element={
              <LiveProvider>
                <HostSelectionProvider>
                  <AppShell />
                </HostSelectionProvider>
              </LiveProvider>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="agents/:id" element={<AgentDetailPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="console" element={<OperatorConsolePage />} />
            <Route path="bulk-operations/:id" element={<BulkOperationPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route
              path="users"
              element={
                <ProtectedRoute roles={["ADMINISTRATOR"]}>
                  <UsersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="settings"
              element={
                <ProtectedRoute roles={["ADMINISTRATOR"]}>
                  <SettingsPage />
                </ProtectedRoute>
              }
            />
            <Route path="unauthorized" element={<UnauthorizedPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
