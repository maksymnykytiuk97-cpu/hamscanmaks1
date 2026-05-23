import "@/App.css";
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "@/components/Dashboard";
import LoginPage from "@/components/LoginPage";
import AdminPanel from "@/components/AdminPanel";
import ProfilePage from "@/components/ProfilePage";
import StatsPage from "@/components/StatsPage";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AuthProvider } from "@/contexts/AuthContext";
import { registerServiceWorker } from "@/lib/push";

function App() {
  useEffect(() => {
    // Register the PWA service worker once on mount. Safe to call repeatedly.
    registerServiceWorker();
  }, []);

  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route 
              path="/" 
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/profile" 
              element={
                <ProtectedRoute>
                  <ProfilePage />
                </ProtectedRoute>
              } 
            />
            <Route
              path="/stats"
              element={
                <ProtectedRoute>
                  <StatsPage />
                </ProtectedRoute>
              }
            />
            <Route 
              path="/admin" 
              element={
                <ProtectedRoute adminOnly={true}>
                  <AdminPanel />
                </ProtectedRoute>
              } 
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
