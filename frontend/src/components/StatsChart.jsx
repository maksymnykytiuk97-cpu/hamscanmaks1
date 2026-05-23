import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from 'recharts';
import { ChartBar } from '@phosphor-icons/react';
import { api } from '@/lib/api';

// Swiss-brutalism palette: high-contrast solids, no gradients.
// Stable per-landlord colour assignment, ordered by appearance.
const PALETTE = ['#002FA7', '#E60023', '#000000', '#FFCB05', '#00875A', '#9F1853', '#7C3AED', '#525252'];

export default function StatsChart() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(14);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get(`/api/stats/daily?days=${days}`)
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [days]);

  if (loading || !data) {
    return (
      <div className="p-6 border border-[#050505] bg-white">
        <div className="font-mono text-xs uppercase tracking-[0.2em] text-[#525252]">Lade Statistik …</div>
      </div>
    );
  }

  const landlords = data.landlords || [];
  // Flatten data so recharts can plot stacked bars by landlord
  const chartData = data.points.map((p) => {
    const row = { date: p.date.slice(5), total: p.total };
    landlords.forEach((l) => { row[l] = p.byLandlord[l] || 0; });
    return row;
  });

  const totalInWindow = data.points.reduce((s, p) => s + p.total, 0);
  const activeDays = data.points.filter((p) => p.total > 0).length;
  const avgPerDay = activeDays > 0 ? (totalInWindow / activeDays).toFixed(1) : '0';
  const peak = data.points.reduce((m, p) => (p.total > m.total ? p : m), { total: 0, date: '—' });

  const colorOf = (i) => PALETTE[i % PALETTE.length];

  return (
    <div className="bg-white border border-[#050505]" data-testid="stats-chart">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#050505]">
        <div className="flex items-center gap-3">
          <ChartBar weight="bold" size={22} />
          <h2 className="text-xl tracking-tight font-bold" style={{ fontFamily: 'Cabinet Grotesk' }}>
            STATISTIK
          </h2>
        </div>
        <div className="flex gap-2">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              data-testid={`stats-range-${d}d`}
              className={`px-3 py-1 text-xs font-mono uppercase tracking-[0.18em] border border-[#050505] transition-colors duration-150 ${
                days === d ? 'bg-[#002FA7] text-white' : 'bg-white text-[#050505] hover:bg-[#F4F4F4]'
              }`}
            >
              {d}T
            </button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-3 border-b border-[#050505]">
        <div className="px-6 py-4 border-r border-[#050505]">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#525252]">Gesamt</div>
          <div className="text-3xl font-bold mt-1" data-testid="stats-total">{totalInWindow}</div>
        </div>
        <div className="px-6 py-4 border-r border-[#050505]">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#525252]">Ø pro aktivem Tag</div>
          <div className="text-3xl font-bold mt-1" data-testid="stats-avg">{avgPerDay}</div>
        </div>
        <div className="px-6 py-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#525252]">Spitzentag</div>
          <div className="text-3xl font-bold mt-1" data-testid="stats-peak">{peak.total}</div>
          <div className="font-mono text-[10px] text-[#525252] mt-1">{peak.date.slice(5)}</div>
        </div>
      </div>

      {/* Chart */}
      <div className="p-6">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
            <CartesianGrid stroke="#E5E5E5" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontFamily: 'monospace', fontSize: 11, fill: '#525252' }}
              axisLine={{ stroke: '#050505' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontFamily: 'monospace', fontSize: 11, fill: '#525252' }}
              axisLine={{ stroke: '#050505' }}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: 'rgba(0,47,167,0.06)' }}
              contentStyle={{
                fontFamily: 'monospace',
                fontSize: 12,
                borderRadius: 0,
                border: '1px solid #050505',
                background: '#ffffff',
              }}
              labelFormatter={(label) => `Datum: ${label}`}
            />
            <Legend
              wrapperStyle={{ fontFamily: 'monospace', fontSize: 11, paddingTop: 12 }}
              iconType="square"
            />
            {landlords.map((l, i) => (
              <Bar key={l} dataKey={l} stackId="a" fill={colorOf(i)} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
