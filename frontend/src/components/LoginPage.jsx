import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Lock, EnvelopeSimple, Buildings } from '@phosphor-icons/react';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    const result = await login(email, password);
    
    setLoading(false);
    
    if (result.success) {
      navigate('/');
    } else {
      setError(result.error || 'Anmeldung fehlgeschlagen');
    }
  };
  
  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo / Title */}
        <div className="border border-[#050505] bg-white p-8 mb-px">
          <div className="flex items-center gap-3 mb-2">
            <Buildings weight="bold" size={32} className="text-[#002FA7]" />
            <div>
              <h1 className="text-3xl tracking-tighter font-black uppercase" style={{ fontFamily: 'Cabinet Grotesk' }}>
                HAMBURG SCANNER
              </h1>
              <p className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">
                IMMOMIO.COM MONITORING
              </p>
            </div>
          </div>
        </div>
        
        {/* Login form */}
        <div className="border border-[#050505] bg-[#F4F4F4] border-t-0 p-8">
          <h2 className="text-2xl tracking-tight font-bold mb-6" style={{ fontFamily: 'Cabinet Grotesk' }}>
            LOGIN
          </h2>
          
          <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form">
            <div>
              <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block">
                E-MAIL
              </Label>
              <div className="relative">
                <EnvelopeSimple 
                  weight="bold" 
                  size={16} 
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" 
                />
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@example.com"
                  required
                  className="rounded-none border-[#050505] bg-white focus-visible:ring-[#002FA7] focus-visible:border-black font-mono pl-10"
                  data-testid="login-email-input"
                />
              </div>
            </div>
            
            <div>
              <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block">
                PASSWORT
              </Label>
              <div className="relative">
                <Lock 
                  weight="bold" 
                  size={16} 
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" 
                />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="rounded-none border-[#050505] bg-white focus-visible:ring-[#002FA7] focus-visible:border-black font-mono pl-10"
                  data-testid="login-password-input"
                />
              </div>
            </div>
            
            {error && (
              <div className="border border-[#FF3B30] bg-[#FF3B30] text-white px-4 py-3" data-testid="login-error">
                <p className="text-xs font-mono uppercase tracking-[0.2em]">{error}</p>
              </div>
            )}
            
            <button
              type="submit"
              disabled={loading}
              className="w-full px-4 py-3 bg-[#002FA7] text-white rounded-none border border-[#050505] hover:bg-black transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="login-submit-button"
            >
              <span className="text-sm font-mono uppercase tracking-[0.2em]">
                {loading ? 'EINLOGGEN...' : 'EINLOGGEN'}
              </span>
            </button>
          </form>
        </div>
        
        <div className="mt-4 text-center">
          <p className="text-xs font-mono text-[#525252]">
            Zugang nur für autorisierte Benutzer
          </p>
        </div>
      </div>
    </div>
  );
}
