import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type AuthUser } from "../api/client";

export type CompanyRegisterInput = {
  company_name: string;
  company_address_line?: string | null;
  company_address_line_2?: string | null;
  company_district?: string | null;
  company_state?: string | null;
  company_pin_code?: string | null;
  company_gstin?: string | null;
  company_phone?: string | null;
  owner_name?: string | null;
  email: string;
  password: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithOtp: (email: string, otp: string, newPassword?: string) => Promise<void>;
  signup: (email: string, password: string, name?: string) => Promise<void>;
  registerCompany: (input: CompanyRegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      const me = await api.get<AuthUser>("/api/auth/me", { skipAuthRedirect: true });
      setUser(me);
    } catch {
      // Only clear session on initial load failures — never log out mid-session
      // because a follow-up /me call failed (e.g. after saving profile).
      setUser((prev) => (prev == null ? null : prev));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const login = useCallback(async (email: string, password: string) => {
    const me = await api.post<AuthUser>("/api/auth/login", { email, password }, { skipAuthRedirect: true });
    setUser(me);
  }, []);

  const loginWithOtp = useCallback(async (email: string, otp: string, newPassword?: string) => {
    const body: { email: string; otp: string; new_password?: string } = { email, otp };
    if (newPassword) body.new_password = newPassword;
    const me = await api.post<AuthUser>("/api/auth/otp-login", body, { skipAuthRedirect: true });
    setUser(me);
  }, []);

  const signup = useCallback(async (email: string, password: string, name?: string) => {
    const me = await api.post<AuthUser>("/api/auth/signup", { email, password, name: name || null }, { skipAuthRedirect: true });
    setUser(me);
  }, []);

  const registerCompany = useCallback(async (input: CompanyRegisterInput) => {
    const me = await api.post<AuthUser>("/api/companies/register", input, { skipAuthRedirect: true });
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout", {});
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, loginWithOtp, signup, registerCompany, logout, refreshMe }),
    [user, loading, login, loginWithOtp, signup, registerCompany, logout, refreshMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
