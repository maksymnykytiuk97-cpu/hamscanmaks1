import { useState, useEffect } from 'react';
import axios from 'axios';
import StatusBar from './StatusBar';
import FilterPanel from './FilterPanel';
import ApartmentList from './ApartmentList';
import { Toaster } from './ui/sonner';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [apartments, setApartments] = useState([]);
  const [scanStatus, setScanStatus] = useState(null);
  const [view, setView] = useState('new'); // 'new' or 'history'
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
    
    // Poll for updates every 30 seconds
    const interval = setInterval(() => {
      fetchApartments();
      fetchScanStatus();
    }, 30000);
    
    return () => clearInterval(interval);
  }, [view, filters]);

  const fetchApartments = async () => {
    try {
      const params = {};
      
      if (filters.minPrice) params.min_price = parseFloat(filters.minPrice);
      if (filters.maxPrice) params.max_price = parseFloat(filters.maxPrice);
      if (filters.minRooms) params.min_rooms = parseInt(filters.minRooms);
      if (filters.maxRooms) params.max_rooms = parseInt(filters.maxRooms);
      
      if (view === 'new') {
        params.status = 'new';
      }
      
      const endpoint = view === 'history' ? `${API}/apartments/history` : `${API}/apartments`;
      const response = await axios.get(endpoint, { params });
      setApartments(response.data);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching apartments:', error);
      toast.error('Fehler beim Laden der Wohnungen');
      setLoading(false);
    }
  };

  const fetchScanStatus = async () => {
    try {
      const response = await axios.get(`${API}/scan-status`);
      setScanStatus(response.data);
    } catch (error) {
      console.error('Error fetching scan status:', error);
    }
  };

  const handleScanNow = async () => {
    try {
      await axios.post(`${API}/scan-now`);
      toast.success('Scan gestartet');
      setTimeout(() => {
        fetchApartments();
        fetchScanStatus();
      }, 5000);
    } catch (error) {
      console.error('Error triggering scan:', error);
      toast.error(error.response?.data?.detail || 'Fehler beim Starten des Scans');
    }
  };

  const handleMarkSeen = async (apartmentId) => {
    try {
      await axios.post(`${API}/apartments/${apartmentId}/mark-seen`);
      toast.success('Als gesehen markiert');
      fetchApartments();
      fetchScanStatus();
    } catch (error) {
      console.error('Error marking apartment as seen:', error);
      toast.error('Fehler beim Markieren');
    }
  };

  return (
    <div className="min-h-screen bg-white">
      <Toaster position="top-right" />
      
      <StatusBar 
        scanStatus={scanStatus} 
        onScanNow={handleScanNow}
      />
      
      <div className="border-t border-[#050505]">
        <div className="grid grid-cols-1 lg:grid-cols-12">
          {/* Filter Panel */}
          <div className="lg:col-span-3 border-r border-[#050505]">
            <FilterPanel 
              filters={filters}
              setFilters={setFilters}
              view={view}
              setView={setView}
            />
          </div>
          
          {/* Main Content */}
          <div className="lg:col-span-9">
            <ApartmentList 
              apartments={apartments}
              loading={loading}
              view={view}
              onMarkSeen={handleMarkSeen}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
