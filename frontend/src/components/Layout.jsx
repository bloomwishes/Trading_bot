import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import StatusBadge from './StatusBadge';
import PaperLiveToggle from './PaperLiveToggle';
import ResetPaperModal from './ResetPaperModal';
import AnimatedNumber from './AnimatedNumber';
import { getStatus, setMode, getPortfolioCurrent } from '../utils/api';
import { Wifi, WifiOff, RefreshCw, Menu, X, QrCode, RotateCcw } from 'lucide-react';
import MobileQRCodeModal from './MobileQRCodeModal';

export default function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [isConnected, setIsConnected] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [qrModalOpen, setQrModalOpen] = useState(false);
  const [resetModalOpen, setResetModalOpen] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await getStatus();
      setStatus(res.data);
      setIsConnected(true);
    } catch {
      setIsConnected(false);
    }
  }, []);

  const fetchPortfolio = useCallback(async () => {
    try {
      const res = await getPortfolioCurrent();
      setPortfolio(res.data);
    } catch {
      // Silently fail
    }
  }, []);

  // Initial fetch and polling
  useEffect(() => {
    fetchStatus();
    fetchPortfolio();

    const interval = setInterval(() => {
      fetchStatus();
      fetchPortfolio();
    }, 10000);

    return () => clearInterval(interval);
  }, [fetchStatus, fetchPortfolio]);

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const handleModeToggle = async (newMode) => {
    try {
      await setMode(newMode);
      await fetchStatus();
    } catch (err) {
      console.error('Failed to set mode:', err);
      throw err;
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchStatus(), fetchPortfolio()]);
    setTimeout(() => setRefreshing(false), 500);
  };

  const currentMode = status?.mode || 'paper';
  const botStatus = status?.running ? 'running' : 'stopped';
  const portfolioValue = portfolio?.total_value_inr || status?.portfolio?.total_value_inr || 0;

  return (
    <div className="flex min-h-screen bg-cyber-bg">
      {/* Sidebar */}
      <Sidebar
        isConnected={isConnected}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main content */}
      <div className="flex-1 min-w-0 lg:ml-64 flex flex-col">
        {/* Top header bar */}
        <header className="sticky top-0 z-30 h-16 border-b border-neon-cyan/10 bg-cyber-bg/80 backdrop-blur-xl flex items-center justify-between px-3 sm:px-6">
          {/* Left section */}
          <div className="flex items-center gap-2 sm:gap-4">
            {/* Hamburger button for mobile */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-neon-cyan transition-all"
              aria-label="Toggle Navigation"
            >
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            <StatusBadge status={botStatus} />
            <PaperLiveToggle
              mode={currentMode}
              onToggle={handleModeToggle}
            />
            {currentMode === 'paper' && (
              <button
                onClick={() => setResetModalOpen(true)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-neon-purple/15 hover:bg-neon-purple/25 border border-neon-purple/40 text-neon-purple text-xs font-heading font-semibold transition-all hover:shadow-[0_0_15px_rgba(180,0,255,0.3)] hover:-translate-y-0.5"
                title="Reset Paper Account: Train AI on trade history, close active trades, clear history, and reset capital"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Reset Paper</span>
              </button>
            )}
          </div>

          {/* Right section */}
          <div className="flex items-center gap-3 sm:gap-6">
            {/* Portfolio value */}
            <button
              onClick={() => navigate('/portfolio')}
              className="text-right group p-1 -m-1 rounded-lg hover:bg-white/5 transition-all text-left sm:text-right cursor-pointer"
              title="Open Portfolio & Asset Holdings"
            >
              <p className="text-[9px] sm:text-[10px] uppercase tracking-wider text-gray-500 group-hover:text-neon-cyan font-heading transition-colors">
                Portfolio ↗
              </p>
              <p className="text-sm sm:text-lg font-bold font-mono text-white group-hover:text-neon-cyan transition-colors">
                <AnimatedNumber
                  value={portfolioValue}
                  prefix="₹"
                  decimals={2}
                />
              </p>
            </button>

            {/* Mobile QR Code button */}
            <button
              onClick={() => setQrModalOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-neon-cyan/10 hover:bg-neon-cyan/20 border border-neon-cyan/30 text-neon-cyan text-xs font-heading font-medium transition-all shadow-[0_0_15px_rgba(0,240,255,0.1)]"
              title="Mobile Access QR Code"
            >
              <QrCode className="w-4 h-4" />
              <span className="hidden sm:inline">Mobile QR</span>
              {status?.tunnel?.tunnel_url && (
                <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />
              )}
            </button>

            {/* Refresh button */}
            <button
              onClick={handleRefresh}
              className="p-1.5 sm:p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-neon-cyan transition-all"
              title="Refresh"
            >
              <RefreshCw
                className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
              />
            </button>

            {/* Connection status */}
            <div className="flex items-center gap-2">
              {isConnected ? (
                <Wifi className="w-4 h-4 text-neon-green/60" />
              ) : (
                <WifiOff className="w-4 h-4 text-neon-red/60" />
              )}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="p-3 sm:p-6 overflow-x-hidden">
          <div
            key={location.pathname}
            className="animate-fade-in"
          >
            <Outlet context={{ status, portfolio, refetchStatus: fetchStatus, refetchPortfolio: fetchPortfolio }} />
          </div>
        </main>

        {/* Mobile QR Code Modal */}
        <MobileQRCodeModal
          isOpen={qrModalOpen}
          onClose={() => setQrModalOpen(false)}
          tunnelData={status?.tunnel}
        />

        {/* Paper Account Reset & Neural Training Modal */}
        <ResetPaperModal
          isOpen={resetModalOpen}
          onClose={() => setResetModalOpen(false)}
          onSuccess={handleRefresh}
        />
      </div>
    </div>
  );
}
