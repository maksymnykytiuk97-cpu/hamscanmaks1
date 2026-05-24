import { MapPin, CurrencyDollar, Resize, Bed, ArrowSquareOut } from '@phosphor-icons/react';

export default function ApartmentList({ apartments, loading, view }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-[#050505] border-t-transparent animate-spin mx-auto mb-4" style={{ borderRadius: 0 }} />
          <p className="text-sm font-mono uppercase tracking-[0.2em]">LADEN...</p>
        </div>
      </div>
    );
  }

  if (apartments.length === 0) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center" data-testid="no-apartments-message">
          <p className="text-xl font-bold mb-2" style={{ fontFamily: 'Cabinet Grotesk' }}>
            KEINE WOHNUNGEN GEFUNDEN
          </p>
          <p className="text-sm text-[#525252]">
            {view === 'new' 
              ? 'Keine neuen Wohnungen in den letzten 24 Stunden. Der Scanner läuft automatisch.'
              : 'Noch keine Wohnungen im Archiv (älter als 24 Stunden).'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl tracking-tight font-bold" style={{ fontFamily: 'Cabinet Grotesk' }}>
          {view === 'new' ? 'NEUE WOHNUNGEN (24 STD)' : 'ARCHIV'}
        </h2>
        <p className="text-sm text-[#525252] font-mono mt-1" data-testid="apartment-count">
          {apartments.length} {apartments.length === 1 ? 'Wohnung' : 'Wohnungen'}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-px bg-[#050505]">
        {(Array.isArray(apartments) ? apartments : []).map((apt, index) => (
          <div 
            key={apt.id} 
            className="bg-white p-6 border border-[#050505] hover:shadow-[4px_4px_0px_#050505] transition-all duration-150"
            data-testid={`apartment-card-${index}`}
          >
            <div className="flex flex-col md:flex-row gap-6">
              {/* Image */}
              {apt.image_url && (
                <div className="md:w-48 h-32 md:h-auto border border-[#050505] overflow-hidden flex-shrink-0">
                  <img 
                    src={apt.image_url} 
                    alt={apt.title}
                    className="w-full h-full object-cover"
                    data-testid={`apartment-image-${index}`}
                  />
                </div>
              )}

              {/* Content */}
              <div className="flex-1">
                {/* Title & Status */}
                <div className="flex items-start justify-between gap-4 mb-3">
                  <h3 
                    className="text-xl font-bold" 
                    style={{ fontFamily: 'Cabinet Grotesk' }}
                    data-testid={`apartment-title-${index}`}
                  >
                    {apt.title}
                  </h3>
                  {(() => {
                    const ageMs = Date.now() - new Date(apt.found_at).getTime();
                    const isNew = ageMs < 24 * 60 * 60 * 1000;
                    return isNew ? (
                      <span 
                        className="px-2 py-1 bg-[#FF3B30] text-white text-xs font-mono uppercase rounded-none whitespace-nowrap"
                        data-testid={`apartment-status-${index}`}
                      >
                        NEU
                      </span>
                    ) : null;
                  })()}
                </div>

                {/* Details */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  {apt.price && (
                    <div className="flex items-center gap-2">
                      <CurrencyDollar weight="bold" size={16} className="text-[#002FA7]" />
                      <span className="text-sm font-mono tracking-tight" data-testid={`apartment-price-${index}`}>
                        €{apt.price.toFixed(2)}
                      </span>
                    </div>
                  )}
                  
                  {apt.rooms && (
                    <div className="flex items-center gap-2">
                      <Bed weight="bold" size={16} className="text-[#002FA7]" />
                      <span className="text-sm font-mono tracking-tight" data-testid={`apartment-rooms-${index}`}>
                        {apt.rooms} {apt.rooms === 1 ? 'Zimmer' : 'Zimmer'}
                      </span>
                    </div>
                  )}
                  
                  {apt.area && (
                    <div className="flex items-center gap-2">
                      <Resize weight="bold" size={16} className="text-[#002FA7]" />
                      <span className="text-sm font-mono tracking-tight" data-testid={`apartment-area-${index}`}>
                        {apt.area}m²
                      </span>
                    </div>
                  )}
                  
                  {apt.district && (
                    <div className="flex items-center gap-2">
                      <MapPin weight="bold" size={16} className="text-[#002FA7]" />
                      <span className="text-sm font-mono tracking-tight" data-testid={`apartment-district-${index}`}>
                        {apt.district}
                      </span>
                    </div>
                  )}
                </div>

                {/* Address */}
                {apt.address && (
                  <div className="mb-2">
                    <p className="text-sm text-[#525252]" data-testid={`apartment-address-${index}`}>
                      📍 {apt.address}
                    </p>
                  </div>
                )}
                
                {/* Landlord */}
                {apt.landlord && (
                  <div className="mb-4">
                    <p className="text-xs font-mono text-[#525252] uppercase tracking-[0.1em]" data-testid={`apartment-landlord-${index}`}>
                      🏢 {apt.landlord}
                    </p>
                  </div>
                )}

                {/* Meta Info */}
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xs font-mono text-[#525252]" data-testid={`apartment-found-at-${index}`}>
                    Gefunden: {new Date(apt.found_at).toLocaleString('de-DE', {
                      day: '2-digit',
                      month: '2-digit',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                </div>

                {/* Actions */}
                <div className="flex flex-wrap gap-2">
                  <a
                    href={apt.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-4 py-2 bg-[#002FA7] text-white rounded-none hover:bg-black transition-colors duration-150 flex items-center gap-2"
                    data-testid={`apartment-view-link-${index}`}
                  >
                    <ArrowSquareOut weight="bold" size={16} />
                    <span className="text-xs font-mono uppercase tracking-[0.2em]">ZUR ANZEIGE</span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
