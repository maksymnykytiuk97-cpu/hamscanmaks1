import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, formatApiErrorDetail } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { 
  ArrowLeft, 
  UserPlus, 
  Trash, 
  Plus, 
  Link as LinkIcon, 
  SignOut,
  EnvelopeSimple,
  Lock,
  User
} from '@phosphor-icons/react';
import { toast, Toaster } from 'sonner';

export default function AdminPanel() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [users, setUsers] = useState([]);
  const [manualUrls, setManualUrls] = useState([]);
  
  const [newUser, setNewUser] = useState({ email: '', password: '', name: '', role: 'user' });
  const [newUrl, setNewUrl] = useState('');
  
  useEffect(() => {
    fetchUsers();
    fetchManualUrls();
  }, []);
  
  const fetchUsers = async () => {
    try {
      const { data } = await api.get('/api/admin/users');
      setUsers(data);
    } catch (e) {
      toast.error('Fehler beim Laden der Benutzer');
    }
  };
  
  const fetchManualUrls = async () => {
    try {
      const { data } = await api.get('/api/admin/manual-urls');
      setManualUrls(data);
    } catch (e) {
      // silent
    }
  };
  
  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      await api.post('/api/admin/users', newUser);
      toast.success('Benutzer erstellt');
      setNewUser({ email: '', password: '', name: '', role: 'user' });
      fetchUsers();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || 'Fehler');
    }
  };
  
  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Benutzer wirklich löschen?')) return;
    try {
      await api.delete(`/api/admin/users/${userId}`);
      toast.success('Benutzer gelöscht');
      fetchUsers();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || 'Fehler');
    }
  };
  
  const handleAddUrl = async (e) => {
    e.preventDefault();
    const loadingToast = toast.loading('URL wird hinzugefügt & Wohnung wird geladen...');
    try {
      const { data } = await api.post('/api/admin/manual-urls', { url: newUrl });
      toast.dismiss(loadingToast);

      const count = data?.apartments_count ?? 0;
      if (data?.type === 'homepage_token') {
        if (count > 0) {
          toast.success(`Landlord-Token hinzugefügt — ${count} neue Wohnung(en) sofort veröffentlicht. Wird alle 3 Min automatisch geprüft.`);
        } else if (data?.parse_error) {
          toast.info(`Token gespeichert: ${data.parse_error}`);
        } else {
          toast.success('Landlord-Token hinzugefügt. Wird alle 3 Min auf neue Wohnungen geprüft.');
        }
      } else if (data?.apartment) {
        const title = data.apartment.title || 'Wohnung';
        toast.success(`URL hinzugefügt — Wohnung gefunden: ${title}`);
      } else if (data?.parse_error) {
        toast.warning(`URL hinzugefügt, aber Wohnung konnte nicht geladen werden: ${data.parse_error}. Wird beim nächsten Scan erneut versucht.`);
      } else {
        toast.success('URL hinzugefügt');
      }

      setNewUrl('');
      fetchManualUrls();
    } catch (err) {
      toast.dismiss(loadingToast);
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || 'Fehler');
    }
  };
  
  const handleRemoveUrl = async (url) => {
    try {
      await api.delete('/api/admin/manual-urls', { data: { url } });
      toast.success('URL entfernt');
      fetchManualUrls();
    } catch (err) {
      toast.error('Fehler beim Entfernen');
    }
  };
  
  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };
  
  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-right" />
      
      {/* Header */}
      <div className="border-b border-[#050505] bg-white">
        <div className="px-8 py-6 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/')}
              className="p-2 border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150"
              data-testid="back-to-dashboard"
            >
              <ArrowLeft weight="bold" size={20} />
            </button>
            <div>
              <h1 className="text-3xl tracking-tighter font-black uppercase" style={{ fontFamily: 'Cabinet Grotesk' }}>
                ADMIN PANEL
              </h1>
              <p className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">
                BENUTZER & URLS VERWALTEN
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <span className="text-xs font-mono uppercase tracking-[0.2em]">
              {user?.email}
            </span>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-[#FF3B30] text-white border border-[#050505] hover:bg-black transition-colors duration-150 flex items-center gap-2"
              data-testid="logout-button"
            >
              <SignOut weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">LOGOUT</span>
            </button>
          </div>
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-[#050505]">
        {/* Users Management */}
        <div className="bg-white p-6 lg:p-8">
          <h2 className="text-2xl tracking-tight font-bold mb-6 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
            <UserPlus weight="bold" size={24} />
            BENUTZER VERWALTUNG
          </h2>
          
          {/* Create User Form */}
          <form onSubmit={handleCreateUser} className="border border-[#050505] bg-[#F4F4F4] p-6 mb-6" data-testid="create-user-form">
            <h3 className="text-sm font-mono uppercase tracking-[0.2em] mb-4">NEUER BENUTZER</h3>
            
            <div className="space-y-3">
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em]">EMAIL</Label>
                <div className="relative mt-1">
                  <EnvelopeSimple weight="bold" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" />
                  <Input
                    type="email"
                    required
                    value={newUser.email}
                    onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                    placeholder="client@example.com"
                    className="rounded-none border-[#050505] bg-white pl-10 font-mono"
                    data-testid="new-user-email"
                  />
                </div>
              </div>
              
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em]">PASSWORT</Label>
                <div className="relative mt-1">
                  <Lock weight="bold" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" />
                  <Input
                    type="password"
                    required
                    minLength={6}
                    value={newUser.password}
                    onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                    placeholder="mindestens 6 Zeichen"
                    className="rounded-none border-[#050505] bg-white pl-10 font-mono"
                    data-testid="new-user-password"
                  />
                </div>
              </div>
              
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em]">NAME (OPTIONAL)</Label>
                <div className="relative mt-1">
                  <User weight="bold" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" />
                  <Input
                    type="text"
                    value={newUser.name}
                    onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                    placeholder="Max Mustermann"
                    className="rounded-none border-[#050505] bg-white pl-10 font-mono"
                    data-testid="new-user-name"
                  />
                </div>
              </div>
              
              <button
                type="submit"
                className="w-full px-4 py-2 bg-[#002FA7] text-white border border-[#050505] hover:bg-black transition-colors duration-150 flex items-center justify-center gap-2"
                data-testid="create-user-submit"
              >
                <Plus weight="bold" size={16} />
                <span className="text-xs font-mono uppercase tracking-[0.2em]">BENUTZER ERSTELLEN</span>
              </button>
            </div>
          </form>
          
          {/* Users List */}
          <div className="space-y-px bg-[#050505] border border-[#050505]">
            {users.map((u) => (
              <div key={u.id} className="bg-white p-4 flex items-center justify-between" data-testid={`user-row-${u.email}`}>
                <div>
                  <p className="font-mono text-sm">{u.email}</p>
                  <p className="text-xs text-[#525252] font-mono uppercase tracking-[0.2em] mt-1">
                    {u.role} {u.name ? `· ${u.name}` : ''}
                  </p>
                </div>
                {u.id !== user?.id && (
                  <button
                    onClick={() => handleDeleteUser(u.id)}
                    className="px-3 py-2 bg-white border border-[#FF3B30] text-[#FF3B30] hover:bg-[#FF3B30] hover:text-white transition-colors duration-150"
                    data-testid={`delete-user-${u.email}`}
                  >
                    <Trash weight="bold" size={16} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
        
        {/* Manual URLs Management */}
        <div className="bg-white p-6 lg:p-8">
          <h2 className="text-2xl tracking-tight font-bold mb-6 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
            <LinkIcon weight="bold" size={24} />
            MANUELLE URLS
          </h2>
          
          <p className="text-xs text-[#525252] mb-4">
            Fügen Sie immomio URLs manuell hinzu — der Scanner überwacht sie automatisch.<br/>
          <strong>Zwei Typen möglich:</strong><br/>
            • <code className="font-mono">tenant.immomio.com/apply/...</code> — Einzelne Wohnung<br/>
            • <code className="font-mono">homepage.immomio.com/de/properties?token=...</code> — Vermieter-Pool (alle Wohnungen, alle 3 Min auto-aktualisiert)
          </p>
          
          {/* Add URL Form */}
          <form onSubmit={handleAddUrl} className="border border-[#050505] bg-[#F4F4F4] p-6 mb-6" data-testid="add-url-form">
            <h3 className="text-sm font-mono uppercase tracking-[0.2em] mb-4">URL HINZUFÜGEN</h3>
            
            <div className="space-y-3">
              <Input
                type="url"
                required
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="tenant.immomio.com/apply/... oder homepage.immomio.com/de/properties?token=..."


                className="rounded-none border-[#050505] bg-white font-mono text-xs"
                data-testid="new-url-input"
              />
              
              <button
                type="submit"
                className="w-full px-4 py-2 bg-[#002FA7] text-white border border-[#050505] hover:bg-black transition-colors duration-150 flex items-center justify-center gap-2"
                data-testid="add-url-submit"
              >
                <Plus weight="bold" size={16} />
                <span className="text-xs font-mono uppercase tracking-[0.2em]">URL HINZUFÜGEN</span>
              </button>
            </div>
          </form>
          
          {/* URLs List */}
          <div className="space-y-px bg-[#050505] border border-[#050505]">
            {manualUrls.length === 0 ? (
              <div className="bg-white p-6 text-center">
                <p className="text-sm font-mono text-[#525252]">Keine manuellen URLs</p>
              </div>
            ) : (
              manualUrls.map((item, idx) => (
                <div key={idx} className="bg-white p-4 flex items-center justify-between gap-4" data-testid={`url-row-${idx}`}>
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {item.type === 'homepage_token' && (
                      <span className="px-2 py-1 bg-[#002FA7] text-white text-[10px] font-mono uppercase tracking-wider flex-shrink-0">
                        POOL
                      </span>
                    )}
                    <a 
                      href={item.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="font-mono text-xs text-[#002FA7] hover:underline break-all"
                    >
                      {item.url}
                    </a>
                  </div>
                  <button
                    onClick={() => handleRemoveUrl(item.url)}
                    className="px-3 py-2 bg-white border border-[#FF3B30] text-[#FF3B30] hover:bg-[#FF3B30] hover:text-white transition-colors duration-150 flex-shrink-0"
                    data-testid={`delete-url-${idx}`}
                  >
                    <Trash weight="bold" size={16} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
