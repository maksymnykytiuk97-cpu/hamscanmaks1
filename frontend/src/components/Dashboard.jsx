import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import StatusBar from './StatusBar';
import FilterPanel from './FilterPanel';
import ApartmentList from './ApartmentList';
import InstallPrompt from './InstallPrompt';
import { Toaster } from './ui/sonner';
import { toast } from 'sonner';
import { Funnel, X as XIcon } from '@phosphor-icons/react';

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [apartments, setApartments] = useState([]);
  const [scanStatus, setScanStatus] = useState(null);
  const [view, setView] = useState('new');
  // Dashboard filters are LOCAL to the browser session (kept in localStorage).
  // They never touch the user's profile so other tabs/users/email-filters stay
  // intact. The profile-level filters (used for email notifications) are
  // edited separately on /profile.
  const [filters, setFilters] = useState(() => {
    try {
      const raw = localStorage.getItem('dashboard_filters');
      if (raw) return JSON.parse(raw);
    } catch (_) { /* ignore */ }
    return { minPrice: '', maxPrice: '', minRooms: '', maxRooms: '' };
  });
  const [loading, setLoading] = useState(true);
  const [filtersLoaded, setFiltersLoaded] = useState(true);
  // Mobile filter drawer (off-canvas, hidden by default on mobile)
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  // Persist filters to localStorage whenever they change.
  useEffect(() => {
    try {
      localStorage.setItem('dashboard_filters', JSON.stringify(filters));
    } catch (_) { /* ignore quota errors */ }
  }, [filters]);

  useEffect(() => {
    if (!filtersLoaded) return;
    fetchApartments();
    fetchScanStatus();
    
    const interval = setInterval(() => {
      fetchApartments();
      fetchScanStatus();
    }, 30000);
    
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, filters, filtersLoaded]);

  // === Live updates via WebSocket ===
  // The backend pushes `new_apartment` and `scan_finished` events. We refresh
  // the listing on either, and show a toast on truly new apartments.
  useEffect(() => {
    if (!filtersLoaded) return;

    // Ask the browser for permission to show OS-level notifications (once)
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      try { Notification.requestPermission(); } catch (_) {}
    }

    // Build a short attention-grabbing "ping" tone using WebAudio.
    // Two short tones (E5 → A5) — friendly, not alarming.
    const playPing = () => {
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        const ctx = new Ctx();
        const playTone = (freq, startTime, duration = 0.18) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.value = freq;
          gain.gain.setValueAtTime(0, startTime);
          gain.gain.linearRampToValueAtTime(0.25, startTime + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);
          osc.connect(gain).connect(ctx.destination);
          osc.start(startTime);
          osc.stop(startTime + duration);
        };
        const t = ctx.currentTime;
        playTone(659.25, t);          // E5
        playTone(880.00, t + 0.15);   // A5
        setTimeout(() => ctx.close().catch(() => {}), 700);
      } catch (_) { /* ignore */ }
    };

    const showDesktopNotification = (apt) => {
      if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
      try {
        const body = [
          apt.price ? `€${apt.price}` : null,
          apt.rooms ? `${apt.rooms} Zi.` : null,
          apt.area ? `${apt.area}m²` : null,
          apt.district || apt.address,
        ].filter(Boolean).join(' · ');
        const n = new Notification(`🏠 Нова квартира в Гамбурзі`, {
          body: `${(apt.title || 'Wohnung').slice(0, 90)}\n${body}`.trim(),
          icon: apt.image_url || '/favicon.ico',
          tag: `apt-${apt.id}`,
          requireInteraction: false,
        });
        n.onclick = () => {
          window.focus();
          if (apt.url) window.open(apt.url, '_blank', 'noopener');
          n.close();
        };
        setTimeout(() => n.close(), 12000);
      } catch (_) { /* ignore */ }
    };

    const httpUrl = process.env.REACT_APP_BACKEND_URL || '';
    const wsUrl = httpUrl.replace(/^http/, 'ws') + '/api/ws/apartments';
    let ws;
    let reconnectTimer;

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'new_apartment') {
              const apt = msg.apartment || {};
              toast.success(`🏠 Нова квартира: ${apt.title?.slice(0, 80) || 'без назви'}`);
              playPing();
              showDesktopNotification(apt);
              fetchApartments();
            } else if (msg.type === 'scan_finished') {
              fetchScanStatus();
              if (msg.new_count > 0) fetchApartments();
            }
          } catch (_) { /* ignore non-JSON */ }
        };
        ws.onclose = () => {
          reconnectTimer = setTimeout(connect, 5000); // auto-reconnect
        };
        ws.onerror = () => { try { ws.close(); } catch (_) {} };
      } catch (_) {
        reconnectTimer = setTimeout(connect, 5000);
      }
    };
    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) {
        ws.onclose = null;
        try { ws.close(); } catch (_) {}
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersLoaded]);

  const fetchApartments = async () => {
    try {
      const params = {};
      
      if (filters.minPrice !== '' && filters.minPrice !== null) params.min_price = parseFloat(filters.minPrice);
      if (filters.maxPrice !== '' && filters.maxPrice !== null) params.max_price = parseFloat(filters.maxPrice);
      if (filters.minRooms !== '' && filters.minRooms !== null) params.min_rooms = parseFloat(filters.minRooms);
      if (filters.maxRooms !== '' && filters.maxRooms !== null) params.max_rooms = parseFloat(filters.maxRooms);
      
      params.status = view === 'history' ? 'history' : 'new';
      
      const response = await api.get('/api/apartments', { params });
      setApartments(Array.isArray(response.data) ? response.data : []);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching apartments:', error);
      setLoading(false);
    }
  };

  const fetchScanStatus = async () => {
    try {
      const response = await api.get('/api/scan-status');
      setScanStatus(response.data);
    } catch (error) {
      console.error('Error fetching scan status:', error);
    }
  };

  const handleScanNow = async () => {
    try {
      await api.post('/api/scan-now');
      toast.success('Scan gestartet');
      setTimeout(() => {
        fetchApartments();
        fetchScanStatus();
      }, 5000);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Fehler beim Starten des Scans');
    }
  };
  
  // Local-only filter setter — no backend call.
  // Profile-level filters (for email notifications) live on /profile.
  const handleFiltersChange = (next) => {
    setFilters((prev) => (typeof next === 'function' ? next(prev) : next));
  };
  
  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-right" />
      <InstallPrompt />

      <StatusBar 
        scanStatus={scanStatus} 
        onScanNow={handleScanNow}
        user={user}
        onLogout={handleLogout}
        onAdminClick={() => navigate('/admin')}
        onProfileClick={() => navigate('/profile')}
        onStatsClick={() => navigate('/stats')}
      />

      <div className="border-t border-[#050505]">
        {/* Mobile filter toggle — sticky top, full-width, only on small screens */}
        <div className="lg:hidden sticky top-0 z-30 bg-white border-b border-[#050505] px-4 py-3 flex items-center justify-between">
          <span className="text-xs font-mono uppercase tracking-[0.2em] text-[#525252]">
            {apartments.length} WOHNUNGEN
          </span>
          <button
            type="button"
            onClick={() => setMobileFilterOpen(true)}
            data-testid="mobile-filter-open"
            className="px-3 py-2 border border-[#050505] bg-white text-[#050505] text-xs font-mono uppercase tracking-[0.18em] hover:bg-[#F4F4F4] transition-colors duration-150 flex items-center gap-2"
          >
            <Funnel weight="bold" size={14} />
            FILTER & ANSICHT
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12">
          {/* Desktop sidebar — hidden on mobile; mobile uses the drawer below */}
          <div className="hidden lg:block lg:col-span-3 border-r border-[#050505]">
            <FilterPanel 
              filters={filters}
              setFilters={handleFiltersChange}
              view={view}
              setView={setView}
            />
          </div>

          {/* Apartments first on mobile — no filter blocking the top */}
          <div className="lg:col-span-9">
            <ApartmentList 
              apartments={apartments}
              loading={loading}
              view={view}
            />
          </div>
        </div>

        {/* Mobile drawer — slides in from the right */}
        {mobileFilterOpen && (
          <div
            className="lg:hidden fixed inset-0 z-50 flex"
            data-testid="mobile-filter-drawer"
          >
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileFilterOpen(false)}
            />
            <div className="relative ml-auto w-[88%] max-w-sm bg-white border-l border-[#050505] overflow-y-auto h-full">
              <div className="sticky top-0 bg-[#050505] text-white px-4 py-3 flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-[0.2em]">FILTER & ANSICHT</span>
                <button
                  type="button"
                  onClick={() => setMobileFilterOpen(false)}
                  data-testid="mobile-filter-close"
                  className="p-1 hover:bg-white/10 transition-colors duration-150"
                  aria-label="Schließen"
                >
                  <XIcon weight="bold" size={20} />
                </button>
              </div>
              <FilterPanel
                filters={filters}
                setFilters={handleFiltersChange}
                view={view}
                setView={(v) => { setView(v); setMobileFilterOpen(false); }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
