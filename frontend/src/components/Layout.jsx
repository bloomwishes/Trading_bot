import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import StatusBadge from './StatusBadge';
import PaperLiveToggle from './PaperLiveToggle';
import AnimatedNumber from './AnimatedNumber';
import { getStatus, setMode, getPortfolioCurrent } from '../utils/api';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';

export default function Layout() {
  const location = useLocation();
  const [status, setStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [isConnected, setIsConnected] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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
      <Sidebar isConnected={isConnected} />

      {/* Main content */}
      <div className="flex-1 ml-64">
        {/* Top header bar */}
        <header className="sticky top-0 z-40 h-16 border-b border-neon-cyan/10 bg-cyber-bg/80 backdrop-blur-xl flex items-center justify-between px-6">
          {/* Left section */}
          <div className="flex items-center gap-4">
            <StatusBadge status={botStatus} />
            <PaperLiveToggle
              mode={currentMode}
              onToggle={handleModeToggle}
            />
          </div>

          {/* Right section */}
          <div className="flex items-center gap-6">
            {/* Portfolio value */}
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-gray-500 font-heading">
                Portfolio Value
              </p>
              <p className="text-lg font-bold font-mono text-white">
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
        <main className="p-6">
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
