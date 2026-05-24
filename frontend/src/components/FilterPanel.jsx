import { Funnel, ClockCounterClockwise, Lightning } from '@phosphor-icons/react';
import { Input } from './ui/input';
import { Label } from './ui/label';

export default function FilterPanel({ filters, setFilters, view, setView }) {
  const handleFilterChange = (field, value) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }));
  };

  return (
    <div className="bg-white p-6">
      {/* View Toggle */}
      <div className="mb-6">
        <h2 className="text-2xl tracking-tight font-bold mb-4" style={{ fontFamily: 'Cabinet Grotesk' }}>
          ANSICHT
        </h2>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setView('new')}
            className={`px-4 py-3 text-left border border-[#050505] rounded-none transition-colors duration-150 ${
              view === 'new'
                ? 'bg-[#002FA7] text-white'
                : 'bg-white text-[#050505] hover:bg-[#F4F4F4]'
            }`}
            data-testid="view-new-button"
          >
            <div className="flex items-center gap-2">
              <Lightning weight="bold" size={18} />
              <span className="text-sm font-mono uppercase tracking-[0.2em]">NEUE</span>
            </div>
          </button>
          
          <button
            onClick={() => setView('history')}
            className={`px-4 py-3 text-left border border-[#050505] rounded-none transition-colors duration-150 ${
              view === 'history'
                ? 'bg-[#002FA7] text-white'
                : 'bg-white text-[#050505] hover:bg-[#F4F4F4]'
            }`}
            data-testid="view-history-button"
          >
            <div className="flex items-center gap-2">
              <ClockCounterClockwise weight="bold" size={18} />
              <span className="text-sm font-mono uppercase tracking-[0.2em]">ARCHIV</span>
            </div>
          </button>
        </div>
      </div>

      <div className="border-t border-[#050505] pt-6">
        <div className="flex items-center gap-2 mb-4">
          <Funnel weight="bold" size={20} />
          <h2 className="text-2xl tracking-tight font-bold" style={{ fontFamily: 'Cabinet Grotesk' }}>
            FILTER
          </h2>
        </div>

        {/* Price Filter */}
        <div className="mb-6">
          <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block">
            PREIS (€)
          </Label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Input
                type="number"
                placeholder="Min"
                value={filters.minPrice}
                onChange={(e) => handleFilterChange('minPrice', e.target.value)}
                className="rounded-none border-[#050505] focus-visible:ring-[#002FA7] focus-visible:border-black font-mono"
                data-testid="filter-price-min"
              />
            </div>
            <div>
              <Input
                type="number"
                placeholder="Max"
                value={filters.maxPrice}
                onChange={(e) => handleFilterChange('maxPrice', e.target.value)}
                className="rounded-none border-[#050505] focus-visible:ring-[#002FA7] focus-visible:border-black font-mono"
                data-testid="filter-price-max"
              />
            </div>
          </div>
        </div>

        {/* Rooms Filter */}
        <div className="mb-6">
          <Label className="text-xs font-mono uppercase tracking-[0.2em] mb-2 block">
            ZIMMER
          </Label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Input
                type="number"
                placeholder="Min"
                value={filters.minRooms}
                onChange={(e) => handleFilterChange('minRooms', e.target.value)}
                className="rounded-none border-[#050505] focus-visible:ring-[#002FA7] focus-visible:border-black font-mono"
                data-testid="filter-rooms-min"
              />
            </div>
            <div>
              <Input
                type="number"
                placeholder="Max"
                value={filters.maxRooms}
                onChange={(e) => handleFilterChange('maxRooms', e.target.value)}
                className="rounded-none border-[#050505] focus-visible:ring-[#002FA7] focus-visible:border-black font-mono"
                data-testid="filter-rooms-max"
              />
            </div>
          </div>
        </div>

        {/* Clear Filters */}
        <button
          onClick={() => setFilters({ minPrice: '', maxPrice: '', minRooms: '', maxRooms: '' })}
          className="w-full px-4 py-2 bg-white border border-[#050505] text-[#050505] rounded-none hover:bg-[#F4F4F4] transition-colors duration-150"
          data-testid="clear-filters-button"
        >
          <span className="text-xs font-mono uppercase tracking-[0.2em]">FILTER ZURÜCKSETZEN</span>
        </button>
      </div>
    </div>
  );
}
