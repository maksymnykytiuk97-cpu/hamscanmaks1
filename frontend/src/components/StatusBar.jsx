import { Broadcast, Buildings, Gear, SignOut, User as UserIcon, ChartBar } from '@phosphor-icons/react';

export default function StatusBar({ scanStatus, onScanNow, user, onLogout, onAdminClick, onProfileClick, onStatsClick }) {
  const formatDateTime = (dateStr) => {
    if (!dateStr) return 'Nie';
    const date = new Date(dateStr);
    return date.toLocaleString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="bg-white border-b border-[#050505]">
      <div className="px-8 py-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-4xl tracking-tighter font-black uppercase" style={{ fontFamily: 'Cabinet Grotesk' }}>
              HAMBURG SCANNER
            </h1>
            <p className="text-sm text-[#525252] mt-1" style={{ fontFamily: 'IBM Plex Sans' }}>
              Immomio.com Wohnungsüberwachung
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 px-4 py-2 border border-[#050505] rounded-none bg-[#F4F4F4]">
              <div className={`w-2 h-2 rounded-full ${
                scanStatus?.is_scanning 
                  ? 'bg-[#00C950] animate-pulse' 
                  : 'bg-[#525252]'
              }`} data-testid="scan-indicator" />
              <span className="text-xs font-mono uppercase tracking-[0.2em]" data-testid="scan-status-text">
                {scanStatus?.is_scanning ? 'SCANNING' : 'BEREIT'}
              </span>
            </div>

            <div className="flex items-center gap-2 px-4 py-2 bg-[#002FA7] text-white rounded-none">
              <Buildings weight="bold" size={16} />
              <span className="text-sm font-mono tracking-tight" data-testid="total-apartments">
                {scanStatus?.total_apartments || 0}
              </span>
            </div>

            <div className="flex items-center gap-2 px-4 py-2 bg-[#FF3B30] text-white rounded-none">
              <span className="text-xs font-mono uppercase tracking-[0.2em]" data-testid="new-apartments-count">
                NEU (24H): {scanStatus?.new_apartments || 0}
              </span>
            </div>

            <button
              onClick={onScanNow}
              disabled={scanStatus?.is_scanning}
              className="px-4 py-2 bg-[#002FA7] text-white rounded-none border border-[#050505] hover:bg-black transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              data-testid="scan-now-button"
            >
              <Broadcast weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">SCAN JETZT</span>
            </button>
            
            {user?.role === 'admin' && (
              <button
                onClick={onAdminClick}
                className="px-4 py-2 bg-white text-[#050505] rounded-none border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150 flex items-center gap-2"
                data-testid="admin-panel-button"
              >
                <Gear weight="bold" size={16} />
                <span className="text-xs font-mono uppercase tracking-[0.2em]">ADMIN</span>
              </button>
            )}
            
            <button
              onClick={onProfileClick}
              className="px-4 py-2 bg-white text-[#050505] rounded-none border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150 flex items-center gap-2"
              data-testid="profile-button"
            >
              <UserIcon weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">PROFIL</span>
              {user?.notifications_enabled && (
                <span className="w-2 h-2 bg-[#00C950] rounded-full animate-pulse" />
              )}
            </button>

            <button
              onClick={onStatsClick}
              className="px-4 py-2 bg-white text-[#050505] rounded-none border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150 flex items-center gap-2"
              data-testid="stats-button"
            >
              <ChartBar weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">STATISTIK</span>
            </button>
            
            <button
              onClick={onLogout}
              className="px-4 py-2 bg-[#FF3B30] text-white rounded-none border border-[#050505] hover:bg-black transition-colors duration-150 flex items-center gap-2"
              data-testid="logout-button"
            >
              <SignOut weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">LOGOUT</span>
            </button>
          </div>
        </div>

        {scanStatus?.last_scan && (
          <div className="mt-4 pt-4 border-t border-[#050505] flex items-center justify-between flex-wrap gap-2">
            <p className="text-xs font-mono text-[#525252]" data-testid="last-scan-info">
              Letzter Scan: {formatDateTime(scanStatus.last_scan)}
            </p>
            {user && (
              <p className="text-xs font-mono text-[#525252]" data-testid="user-info">
                Angemeldet als: {user.email} {user.role === 'admin' && '(ADMIN)'}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
