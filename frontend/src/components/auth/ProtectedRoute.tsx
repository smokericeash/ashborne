import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../context/useAuth";
import type { Role } from "../../types";
import { PageLoader } from "../ui";

export function ProtectedRoute({
  roles,
  children,
}: {
  roles?: Role[];
  children?: ReactNode;
}) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.loading) return <PageLoader />;
  if (!auth.isAuthenticated)
    return <Navigate to="/login" replace state={{ from: location }} />;
  if (roles && !auth.hasRole(...roles))
    return <Navigate to="/unauthorized" replace />;
  return children ?? <Outlet />;
}

export function PermissionGate({
  roles,
  children,
  fallback = null,
}: {
  roles: Role[];
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const auth = useAuth();
  return auth.hasRole(...roles) ? children : fallback;
}
