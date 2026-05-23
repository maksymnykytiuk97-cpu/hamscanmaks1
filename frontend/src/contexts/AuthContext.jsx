import { createContext, useContext, useEffect, useState } from 'react';
import { api, formatApiErrorDetail } from '@/lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = not authenticated, object = authenticated
  
  useEffect(() => {
    checkAuth();
  }, []);
  
  const checkAuth = async () => {
    try {
      const { data } = await api.get('/api/auth/me');
      setUser(data);
    } catch (e) {
      setUser(false);
    }
  };
  
  const login = async (email, password) => {
    try {
      const { data } = await api.post('/api/auth/login', { email, password });
      setUser(data);
      return { success: true };
    } catch (e) {
      return { 
        success: false, 
        error: formatApiErrorDetail(e.response?.data?.detail) || e.message 
      };
    }
  };
  
  const logout = async () => {
    try {
      await api.post('/api/auth/logout');
    } catch (e) {
      // ignore
    }
    setUser(false);
  };
  
  return (
    <AuthContext.Provider value={{ user, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
