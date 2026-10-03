import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    try { const { data } = await api.get("/auth/me"); setUser(data.user); }
    catch { setUser(null); } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const login = async (email, password) => { const { data } = await api.post("/auth/login", { email, password }); setUser(data.user); return data.user; };
  const register = async (email, password, name) => { const { data } = await api.post("/auth/register", { email, password, name }); setUser(data.user); return data.user; };
  const logout = async () => { try { await api.post("/auth/logout"); } catch {} setUser(null); };
  return <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
