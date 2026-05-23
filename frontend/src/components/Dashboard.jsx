import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import StatusBar from './StatusBar';
import FilterPanel from './FilterPanel';
import ApartmentList from './ApartmentList';
import { Toaster } from './ui/sonner';
import { toast } from 'sonner';

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [apartments, setApartments] = useState([]);
  const [scanStatus, setScanStatus] = useState(null);
  const [view, setView] = useState('new');
  const [filters, setFilters] = useState({
    minPrice: '',
    maxPrice: '',
    minRooms: '',
    maxRooms: ''
  });
  const [loading, setLoading] = useState(true);
  const [filtersLoaded, setFiltersLoaded] = useState(false);

  // Load user's personal filters from profile on mount
  useEffect(() => {
    const loadFilters = async () => {
      try {
        const { data } = await api.get('/api/profile');
        setFilters({
          minPrice: data.min_price ?? '',
          maxPrice: data.max_price ?? '',
          minRooms: data.min_rooms ?? '',
          maxRooms: data.max_rooms ?? '',
        });
      } catch (e) {
        // Continue with default empty filters
      } finally {
        setFiltersLoaded(true);
      }
    };
    loadFilters();
  }, []);

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

  const fetchApartments = async () => {
    try {
      const params = {};
      
      if (filters.minPrice !== '' && filters.minPrice !== null) params.min_price = parseFloat(filters.minPrice);
      if (filters.maxPrice !== '' && filters.maxPrice !== null) params.max_price = parseFloat(filters.maxPrice);
      if (filters.minRooms !== '' && filters.minRooms !== null) params.min_rooms = parseFloat(filters.minRooms);
      if (filters.maxRooms !== '' && filters.maxRooms !== null) params.max_rooms = parseFloat(filters.maxRooms);
      
      params.status = view === 'history' ? 'history' : 'new';
      
      const response = await api.get('/api/apartments', { params });
      setApartments(response.data);
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
  
  // Save filters to user profile (debounced via explicit save)
  const handleFiltersChange = async (newFilters) => {
    setFilters(newFilters);
    // Persist to profile
    try {
      await api.put('/api/profile', {
        notification_email: user?.notification_email || user?.email,
        notifications_enabled: user?.notifications_enabled ?? false,
        min_price: newFilters.minPrice === '' ? null : parseFloat(newFilters.minPrice),
        max_price: newFilters.maxPrice === '' ? null : parseFloat(newFilters.maxPrice),
        min_rooms: newFilters.minRooms === '' ? null : parseFloat(newFilters.minRooms),
        max_rooms: newFilters.maxRooms === '' ? null : parseFloat(newFilters.maxRooms),
      });
    } catch (e) {
      // silent
    }
  };
  
  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-right" />
      
      <StatusBar 
        scanStatus={scanStatus} 
        onScanNow={handleScanNow}
        user={user}
        onLogout={handleLogout}
        onAdminClick={() => navigate('/admin')}
        onProfileClick={() => navigate('/profile')}
      />
      
      <div className="border-t border-[#050505]">
        <div className="grid grid-cols-1 lg:grid-cols-12">
          <div className="lg:col-span-3 border-r border-[#050505]">
            <FilterPanel 
              filters={filters}
              setFilters={handleFiltersChange}
              view={view}
              setView={setView}
            />
          </div>
          
          <div className="lg:col-span-9">
            <ApartmentList 
              apartments={apartments}
              loading={loading}
              view={view}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
