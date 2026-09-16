import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { User } from "../types";
import { api, onSessionUpdated, onUnauthorized } from "../services/api";
import { tokenStore } from "../services/tokenStore";
import { AuthContext, type AuthContextValue } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(
    Boolean(tokenStore.getAccess() || tokenStore.getRefresh()),
  );

  const clearSession = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    onUnauthorized(clearSession);
    onSessionUpdated(setUser);
    return () => {
      onUnauthorized(null);
      onSessionUpdated(null);
    };
  }, [clearSession]);

  useEffect(() => {
    if (!tokenStore.getAccess() && !tokenStore.getRefresh()) {
      setLoading(false);
      return;
    }
    let active = true;
    api.auth
      .me()
      .then((currentUser) => active && setUser(currentUser))
      .catch(() => active && clearSession())
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [clearSession]);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.auth.login(email.trim().toLowerCase(), password);
    tokenStore.set(session.access_token, session.refresh_token);
    setUser(session.user ?? (await api.auth.me()));
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefresh();
    try {
      await api.auth.logout(refreshToken);
    } catch {
      // Local logout still completes if the server is unreachable.
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user),
      login,
      logout,
      hasRole: (...roles) => Boolean(user && roles.includes(user.role)),
    }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
