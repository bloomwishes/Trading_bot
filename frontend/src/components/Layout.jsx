import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import StatusBadge from './StatusBadge';
import PaperLiveToggle from './PaperLiveToggle';
import AnimatedNumber from './AnimatedNumber';
import { getStatus, setMode, getPortfolioCurrent } from '../utils/api';
import { Wifi, WifiOff, RefreshCw, Menu } from 'lucide-react';

export default function Layout() {
  const location = useLocation();
  const [status, setStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [isConnected, setIsConnected] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main content */}
      <div className="flex-1 w-full lg:ml-64 min-w-0">
        {/* Top header bar */}
        <header className="sticky top-0 z-30 h-16 border-b border-white/[0.06] bg-cyber-bg/85 backdrop-blur-xl flex items-center justify-between gap-3 px-4 sm:px-6">
          {/* Left section */}
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 -ml-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 shrink-0"
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <StatusBadge status={botStatus} />
            <div className="hidden sm:block">
              <PaperLiveToggle mode={currentMode} onToggle={handleModeToggle} />
            </div>
          </div>

          {/* Right section */}
          <div className="flex items-center gap-3 sm:gap-6 shrink-0">
            {/* Portfolio value */}
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-heading">
                Portfolio
              </p>
              <p className="text-base sm:text-lg font-bold font-mono text-white">
                <AnimatedNumber
                  value={portfolioValue}
                  prefix="₹"
                  decimals={2}
                />
              </p>
            </div>

            {/* Refresh button */}
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-white/5 text-gray-400 hover:text-neon-cyan transition-all"
              title="Refresh"
            >
              <RefreshCw
                className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
              />
            </button>

            {/* Connection status */}
            <div className="hidden sm:flex items-center gap-2">
              {isConnected ? (
                <Wifi className="w-4 h-4 text-neon-green/60" />
              ) : (
                <WifiOff className="w-4 h-4 text-neon-red/60" />
              )}
            </div>
          </div>
        </header>

        {/* Mobile-only mode toggle row */}
        <div className="sm:hidden flex items-center px-4 py-3 border-b border-white/[0.06]">
          <PaperLiveToggle mode={currentMode} onToggle={handleModeToggle} />
        </div>

        {/* Page content */}
        <main className="p-4 sm:p-6 max-w-[1600px] mx-auto">
          <div
            key={location.pathname}
            className="animate-fade-in"
          >
            <Outlet context={{ status, portfolio, refetchStatus: fetchStatus, refetchPortfolio: fetchPortfolio }} />
          </div>
        </main>
      </div>
    </div>
  );
}
