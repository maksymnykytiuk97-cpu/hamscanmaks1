import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import StatusBar from './StatusBar';
import FilterPanel from './FilterPanel';
import ApartmentList from './ApartmentList';
import { Toaster } from './ui/sonner';
import { toast } from 'sonner';
import { Gear, SignOut } from '@phosphor-icons/react';

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

  useEffect(() => {
    fetchApartments();
    fetchScanStatus();
    
    const interval = setInterval(() => {
      fetchApartments();
      fetchScanStatus();
    }, 30000);
    
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, filters]);

  const fetchApartments = async () => {
    try {
      const params = {};
      
      if (filters.minPrice) params.min_price = parseFloat(filters.minPrice);
      if (filters.maxPrice) params.max_price = parseFloat(filters.maxPrice);
      if (filters.minRooms) params.min_rooms = parseFloat(filters.minRooms);
      if (filters.maxRooms) params.max_rooms = parseFloat(filters.maxRooms);
      
      if (view === 'new') {
        params.status = 'new';
      }
      
      const endpoint = view === 'history' ? '/api/apartments/history' : '/api/apartments';
      const response = await api.get(endpoint, { params });
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
              setFilters={setFilters}
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
