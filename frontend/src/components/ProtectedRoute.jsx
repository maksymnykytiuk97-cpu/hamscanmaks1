import { Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user } = useAuth();
  
  if (user === null) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-[#050505] border-t-transparent animate-spin mx-auto mb-4" style={{ borderRadius: 0 }} />
          <p className="text-sm font-mono uppercase tracking-[0.2em]">LADEN...</p>
        </div>
      </div>
    );
  }
  
  if (user === false) {
    return <Navigate to="/login" replace />;
  }
  
  if (adminOnly && user.role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  
  return children;
}
