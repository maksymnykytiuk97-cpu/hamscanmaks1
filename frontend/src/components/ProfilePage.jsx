import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, formatApiErrorDetail } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Checkbox } from './ui/checkbox';
import { 
  ArrowLeft, 
  EnvelopeSimple, 
  User as UserIcon,
  FloppyDisk,
  Bell,
  BellSlash
} from '@phosphor-icons/react';
import { toast, Toaster } from 'sonner';

export default function ProfilePage() {
  const { user, checkAuth } = useAuth();
  const navigate = useNavigate();
  
  const [profile, setProfile] = useState({
    notification_email: '',
    notifications_enabled: false
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  useEffect(() => {
    fetchProfile();
  }, []);
  
  const fetchProfile = async () => {
    try {
      const { data } = await api.get('/api/profile');
      setProfile({
        notification_email: data.notification_email || '',
        notifications_enabled: data.notifications_enabled || false
      });
      setLoading(false);
    } catch (e) {
      toast.error('Fehler beim Laden des Profils');
      setLoading(false);
    }
  };
  
  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put('/api/profile', profile);
      await checkAuth();
      toast.success('Profil gespeichert');
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || 'Fehler beim Speichern');
    }
    setSaving(false);
  };
  
  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-[#050505] border-t-transparent animate-spin" style={{ borderRadius: 0 }} />
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-right" />
      
      {/* Header */}
      <div className="border-b border-[#050505] bg-white">
        <div className="px-8 py-6 flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150"
            data-testid="back-to-dashboard"
          >
            <ArrowLeft weight="bold" size={20} />
          </button>
          <div>
            <h1 className="text-3xl tracking-tighter font-black uppercase" style={{ fontFamily: 'Cabinet Grotesk' }}>
              MEIN PROFIL
            </h1>
            <p className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">
              E-MAIL BENACHRICHTIGUNGEN VERWALTEN
            </p>
          </div>
        </div>
      </div>
      
      {/* Profile Form */}
      <div className="max-w-2xl mx-auto p-8">
        <div className="border border-[#050505] bg-white">
          {/* Account Info Section */}
          <div className="p-6 border-b border-[#050505] bg-[#F4F4F4]">
            <h2 className="text-xl tracking-tight font-bold mb-4 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
              <UserIcon weight="bold" size={20} />
              KONTO
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">LOGIN E-MAIL</Label>
                <p className="font-mono text-sm mt-1" data-testid="account-email">{user?.email}</p>
              </div>
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">ROLLE</Label>
                <p className="font-mono text-sm mt-1 uppercase" data-testid="account-role">{user?.role}</p>
              </div>
            </div>
          </div>
          
          {/* Notification Settings */}
          <form onSubmit={handleSave} className="p-6" data-testid="profile-form">
            <h2 className="text-xl tracking-tight font-bold mb-4 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
              <Bell weight="bold" size={20} />
              BENACHRICHTIGUNGEN
            </h2>
            
            <div className="space-y-6">
              {/* Notification Email */}
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block">
                  BENACHRICHTIGUNGS E-MAIL
                </Label>
                <div className="relative">
                  <EnvelopeSimple weight="bold" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#525252]" />
                  <Input
                    type="email"
                    value={profile.notification_email}
                    onChange={(e) => setProfile({ ...profile, notification_email: e.target.value })}
                    placeholder="ihre@email.com"
                    className="rounded-none border-[#050505] bg-white pl-10 font-mono"
                    data-testid="notification-email-input"
                  />
                </div>
                <p className="text-xs text-[#525252] mt-2">
                  An diese E-Mail werden Benachrichtigungen über neue Wohnungen gesendet.
                </p>
              </div>
              
              {/* Enable Notifications Checkbox */}
              <div className="border border-[#050505] bg-[#F4F4F4] p-4">
                <label className="flex items-start gap-3 cursor-pointer" data-testid="notifications-toggle-label">
                  <input
                    type="checkbox"
                    checked={profile.notifications_enabled}
                    onChange={(e) => setProfile({ ...profile, notifications_enabled: e.target.checked })}
                    className="mt-1 w-5 h-5 border border-[#050505] rounded-none accent-[#002FA7] cursor-pointer"
                    data-testid="notifications-enabled-checkbox"
                  />
                  <div>
                    <p className="font-bold text-sm flex items-center gap-2">
                      {profile.notifications_enabled ? (
                        <Bell weight="bold" size={16} className="text-[#00C950]" />
                      ) : (
                        <BellSlash weight="bold" size={16} className="text-[#525252]" />
                      )}
                      E-MAIL BENACHRICHTIGUNGEN AKTIVIEREN
                    </p>
                    <p className="text-xs text-[#525252] mt-1">
                      Aktivieren Sie diese Option, um automatisch E-Mails zu erhalten, wenn neue Wohnungen in Hamburg gefunden werden.
                    </p>
                  </div>
                </label>
              </div>
              
              {/* Status Indicator */}
              <div className={`border border-[#050505] p-4 ${profile.notifications_enabled ? 'bg-[#00C950]/10' : 'bg-[#F4F4F4]'}`}>
                <p className="text-xs font-mono uppercase tracking-[0.2em]">
                  STATUS: {profile.notifications_enabled ? (
                    <span className="text-[#00C950]">✓ AKTIV - SIE ERHALTEN BENACHRICHTIGUNGEN</span>
                  ) : (
                    <span className="text-[#525252]">PAUSIERT</span>
                  )}
                </p>
              </div>
              
              {/* Save Button */}
              <button
                type="submit"
                disabled={saving}
                className="w-full px-4 py-3 bg-[#002FA7] text-white rounded-none border border-[#050505] hover:bg-black transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                data-testid="save-profile-button"
              >
                <FloppyDisk weight="bold" size={16} />
                <span className="text-sm font-mono uppercase tracking-[0.2em]">
                  {saving ? 'SPEICHERN...' : 'PROFIL SPEICHERN'}
                </span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
