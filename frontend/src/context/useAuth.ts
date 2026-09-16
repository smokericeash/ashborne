import { createContext, useContext } from "react";
import type { Role, User } from "../types";

export interface AuthContextValue {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
