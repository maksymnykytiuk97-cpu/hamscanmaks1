import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from '@phosphor-icons/react';
import StatsChart from './StatsChart';

export default function StatsPage() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-[#F4F4F4]">
      {/* Header */}
      <div className="bg-white border-b border-[#050505]">
        <div className="px-8 py-6 flex items-center justify-between">
          <div>
            <h1
              className="text-4xl tracking-tighter font-black uppercase"
              style={{ fontFamily: 'Cabinet Grotesk' }}
            >
              STATISTIK
            </h1>
            <p className="text-sm text-[#525252] mt-1" style={{ fontFamily: 'IBM Plex Sans' }}>
              Tägliche Anzahl gefundener Wohnungen, gruppiert nach Anbieter.
            </p>
          </div>
          <button
            onClick={() => navigate('/')}
            data-testid="stats-back-button"
            className="px-4 py-2 bg-white text-[#050505] border border-[#050505] hover:bg-[#F4F4F4] transition-colors duration-150 flex items-center gap-2"
          >
            <ArrowLeft weight="bold" size={16} />
            <span className="text-xs font-mono uppercase tracking-[0.2em]">ZURÜCK</span>
          </button>
        </div>
      </div>

      <div className="px-8 py-8 max-w-6xl">
        <StatsChart />
      </div>
    </div>
  );
}
