import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, formatApiErrorDetail } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { 
  ArrowLeft, 
  EnvelopeSimple, 
  User as UserIcon,
  FloppyDisk,
  Bell,
  BellSlash,
  Funnel,
  CurrencyDollar,
  Bed,
  DeviceMobile
} from '@phosphor-icons/react';
import { toast, Toaster } from 'sonner';
import {
  isPushSupported,
  subscribeToPush,
  unsubscribeFromPush,
  getCurrentSubscription,
  sendTestPush,
} from '@/lib/push';

export default function ProfilePage() {
  const { user, checkAuth } = useAuth();
  const navigate = useNavigate();
  
  const [profile, setProfile] = useState({
    notification_email: '',
    notifications_enabled: false,
    min_price: '',
    max_price: '',
    min_rooms: '',
    max_rooms: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Push notification state
  const [pushSupported] = useState(() => isPushSupported());
  const [pushSubscribed, setPushSubscribed] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);

  useEffect(() => {
    fetchProfile();
    if (isPushSupported()) {
      getCurrentSubscription().then((s) => setPushSubscribed(!!s)).catch(() => {});
    }
  }, []);

  const handlePushToggle = async () => {
    setPushBusy(true);
    try {
      if (pushSubscribed) {
        await unsubscribeFromPush();
        setPushSubscribed(false);
        toast.success('Push-Benachrichtigungen deaktiviert');
      } else {
        await subscribeToPush();
        setPushSubscribed(true);
        toast.success('Push-Benachrichtigungen aktiviert!');
      }
    } catch (e) {
      toast.error(e?.message || 'Fehler bei Push-Einstellungen');
    } finally {
      setPushBusy(false);
    }
  };

  const handlePushTest = async () => {
    setPushBusy(true);
    try {
      const res = await sendTestPush();
      toast.success(`Test-Push gesendet (${res?.sent || 0} Gerät(e))`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e) || 'Test-Push fehlgeschlagen');
    } finally {
      setPushBusy(false);
    }
  };
  
  const fetchProfile = async () => {
    try {
      const { data } = await api.get('/api/profile');
      setProfile({
        notification_email: data.notification_email || '',
        notifications_enabled: data.notifications_enabled || false,
        min_price: data.min_price ?? '',
        max_price: data.max_price ?? '',
        min_rooms: data.min_rooms ?? '',
        max_rooms: data.max_rooms ?? '',
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
      const payload = {
        notification_email: profile.notification_email,
        notifications_enabled: profile.notifications_enabled,
        min_price: profile.min_price === '' ? null : parseFloat(profile.min_price),
        max_price: profile.max_price === '' ? null : parseFloat(profile.max_price),
        min_rooms: profile.min_rooms === '' ? null : parseFloat(profile.min_rooms),
        max_rooms: profile.max_rooms === '' ? null : parseFloat(profile.max_rooms),
      };
      await api.put('/api/profile', payload);
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
              PERSÖNLICHE EINSTELLUNGEN
            </p>
          </div>
        </div>
      </div>
      
      <div className="max-w-3xl mx-auto p-8">
        <form onSubmit={handleSave} data-testid="profile-form" className="space-y-px bg-[#050505]">
          {/* Account Info */}
          <div className="bg-[#F4F4F4] p-6 border border-[#050505]">
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
          
          {/* Notifications */}
          <div className="bg-white p-6 border border-[#050505]">
            <h2 className="text-xl tracking-tight font-bold mb-4 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
              <Bell weight="bold" size={20} />
              BENACHRICHTIGUNGEN
            </h2>
            
            <div className="space-y-4">
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
              </div>
              
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
                      Erhalten Sie automatische E-Mails über neue Wohnungen, die Ihren Filtern entsprechen.
                    </p>
                  </div>
                </label>
              </div>

              {/* Push notifications (PWA) */}
              <div className="border border-[#050505] bg-[#F4F4F4] p-4" data-testid="push-section">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-start gap-3 flex-1 min-w-[260px]">
                    <DeviceMobile
                      weight="bold"
                      size={28}
                      className={pushSubscribed ? 'text-[#00C950] mt-1' : 'text-[#525252] mt-1'}
                    />
                    <div>
                      <p className="font-bold text-sm uppercase tracking-tight">PUSH-BENACHRICHTIGUNGEN</p>
                      <p className="text-xs text-[#525252] mt-1">
                        Sofort-Push aufs Gerät (auch bei geschlossenem Browser), gefiltert nach Ihren persönlichen Einstellungen.
                      </p>
                      {!pushSupported && (
                        <p className="text-xs text-[#E60023] mt-2 font-mono">
                          Dieser Browser unterstützt keine Push-Benachrichtigungen.
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handlePushToggle}
                      disabled={!pushSupported || pushBusy}
                      data-testid="push-toggle-button"
                      className={`px-4 py-2 border border-[#050505] text-xs font-mono uppercase tracking-[0.18em] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed ${
                        pushSubscribed ? 'bg-[#FF3B30] text-white hover:bg-black' : 'bg-[#002FA7] text-white hover:bg-black'
                      }`}
                    >
                      {pushBusy ? '…' : pushSubscribed ? 'DEAKTIVIEREN' : 'AKTIVIEREN'}
                    </button>
                    {pushSubscribed && (
                      <button
                        type="button"
                        onClick={handlePushTest}
                        disabled={pushBusy}
                        data-testid="push-test-button"
                        className="px-4 py-2 border border-[#050505] bg-white text-[#050505] text-xs font-mono uppercase tracking-[0.18em] hover:bg-[#F4F4F4] transition-colors duration-150 disabled:opacity-50"
                      >
                        TEST
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          {/* Personal Filters */}
          <div className="bg-white p-6 border border-[#050505]">
            <h2 className="text-xl tracking-tight font-bold mb-2 flex items-center gap-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
              <Funnel weight="bold" size={20} />
              PERSÖNLICHE FILTER
            </h2>
            <p className="text-xs text-[#525252] mb-4">
              Diese Filter gelten nur für Ihr Konto. Andere Benutzer haben ihre eigenen Filter.
            </p>
            
            <div className="space-y-4">
              {/* Price */}
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block flex items-center gap-1">
                  <CurrencyDollar weight="bold" size={14} />
                  PREIS (€) - MIETE PRO MONAT
                </Label>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    type="number"
                    value={profile.min_price}
                    onChange={(e) => setProfile({ ...profile, min_price: e.target.value })}
                    placeholder="Min (€)"
                    className="rounded-none border-[#050505] bg-white font-mono"
                    data-testid="profile-min-price"
                  />
                  <Input
                    type="number"
                    value={profile.max_price}
                    onChange={(e) => setProfile({ ...profile, max_price: e.target.value })}
                    placeholder="Max (€)"
                    className="rounded-none border-[#050505] bg-white font-mono"
                    data-testid="profile-max-price"
                  />
                </div>
              </div>
              
              {/* Rooms */}
              <div>
                <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block flex items-center gap-1">
                  <Bed weight="bold" size={14} />
                  ZIMMER
                </Label>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    type="number"
                    step="0.5"
                    value={profile.min_rooms}
                    onChange={(e) => setProfile({ ...profile, min_rooms: e.target.value })}
                    placeholder="Min"
                    className="rounded-none border-[#050505] bg-white font-mono"
                    data-testid="profile-min-rooms"
                  />
                  <Input
                    type="number"
                    step="0.5"
                    value={profile.max_rooms}
                    onChange={(e) => setProfile({ ...profile, max_rooms: e.target.value })}
                    placeholder="Max"
                    className="rounded-none border-[#050505] bg-white font-mono"
                    data-testid="profile-max-rooms"
                  />
                </div>
              </div>
              
              <p className="text-xs text-[#525252] italic">
                Leere Felder = kein Filter. Beispiel: nur Max-Preis = 1500€ filtert Wohnungen bis 1500€.
              </p>
            </div>
          </div>
          
          {/* Save */}
          <div className="bg-white p-6 border border-[#050505]">
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
  );
}
