import { useEffect, useState } from 'react';
import { Broadcast, Clock, Buildings } from '@phosphor-icons/react';

export default function StatusBar({ scanStatus, onScanNow }) {
  const [countdown, setCountdown] = useState(180); // 3 minutes in seconds

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          return 180; // Reset to 3 minutes
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

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
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          {/* Title */}
          <div>
            <h1 className="text-4xl tracking-tighter font-black uppercase" style={{ fontFamily: 'Cabinet Grotesk' }}>
              HAMBURG SCANNER
            </h1>
            <p className="text-sm text-[#525252] mt-1" style={{ fontFamily: 'IBM Plex Sans' }}>
              Immomio.com Wohnungsüberwachung
            </p>
          </div>

          {/* Status Info */}
          <div className="flex flex-wrap items-center gap-4">
            {/* Scanning Status */}
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

            {/* Next Scan Countdown */}
            <div className="flex items-center gap-2 px-4 py-2 border border-[#050505] rounded-none">
              <Clock weight="bold" size={16} />
              <span className="text-sm font-mono tracking-tight" data-testid="next-scan-countdown">
                {formatTime(countdown)}
              </span>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-2 px-4 py-2 bg-[#002FA7] text-white rounded-none">
              <Buildings weight="bold" size={16} />
              <span className="text-sm font-mono tracking-tight" data-testid="total-apartments">
                {scanStatus?.total_apartments || 0}
              </span>
            </div>

            <div className="flex items-center gap-2 px-4 py-2 bg-[#FF3B30] text-white rounded-none">
              <span className="text-xs font-mono uppercase tracking-[0.2em]" data-testid="new-apartments-count">
                NEU: {scanStatus?.new_apartments || 0}
              </span>
            </div>

            {/* Manual Scan Button */}
            <button
              onClick={onScanNow}
              disabled={scanStatus?.is_scanning}
              className="px-4 py-2 bg-[#002FA7] text-white rounded-none border border-[#050505] hover:bg-black transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              data-testid="scan-now-button"
            >
              <Broadcast weight="bold" size={16} />
              <span className="text-xs font-mono uppercase tracking-[0.2em]">SCAN JETZT</span>
            </button>
          </div>
        </div>

        {/* Last Scan Info */}
        {scanStatus?.last_scan && (
          <div className="mt-4 pt-4 border-t border-[#050505]">
            <p className="text-xs font-mono text-[#525252]" data-testid="last-scan-info">
              Letzter Scan: {formatDateTime(scanStatus.last_scan)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
