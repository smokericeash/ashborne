import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/auth/ProtectedRoute";
import { AppShell } from "./components/layout/AppShell";
import { LiveProvider } from "./context/LiveContext";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AgentsPage } from "./pages/AgentsPage";
import { AuditPage } from "./pages/AuditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { SettingsPage } from "./pages/SettingsPage";
import { NotFoundPage, UnauthorizedPage } from "./pages/SystemPages";
import { TasksPage } from "./pages/TasksPage";
import { UsersPage } from "./pages/UsersPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route
          element={
            <LiveProvider>
              <AppShell />
            </LiveProvider>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="agents/:id" element={<AgentDetailPage />} />
          <Route path="tasks" element={<TasksPage />} />
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
  );
}
