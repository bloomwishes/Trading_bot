import React, { useState, useEffect } from 'react';
import { Activity, CheckCircle2, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { getDiagnostics } from '../utils/api';

export default function Diagnostics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDiagnostics = async () => {
    try {
      const res = await getDiagnostics();
      setData(res.data);
      setError(null);
    } catch (err) {
      setError('Failed to reach backend diagnostics API.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
    const intervalId = setInterval(fetchDiagnostics, 10000); // Auto-refresh every 10 seconds
    return () => clearInterval(intervalId);
  }, []);

  const getStatusIcon = (status) => {
    if (status === 'ok') return <CheckCircle2 className="text-neon-green" size={24} />;
    if (status === 'warning') return <AlertTriangle className="text-neon-yellow" size={24} />;
    return <XCircle className="text-neon-red" size={24} />;
  };

  const checkConfigs = [
    { key: 'database', title: 'Database Connection', desc: 'Connectivity to PostgreSQL/SQLite' },
    { key: 'local_ai', title: 'Local AI (Ollama)', desc: 'AI agent reasoning engine status' },
    { key: 'market_data', title: 'Exchange Market Data', desc: 'Live candle data feed from CoinDCX' },
    { key: 'watchlist', title: 'Watchlist Configuration', desc: 'Coins configured for scanning' },
    { key: 'strategies', title: 'Active Strategies', desc: 'Trading rule engines enabled' },
    { key: 'risk', title: 'Risk Limits', desc: 'Capital protection & daily loss limits' },
    { key: 'engine', title: 'Core Trading Engine', desc: 'Background scanner and order execution' }
  ];

  if (loading && !data) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="h-10 w-64 bg-cyber-surface/50 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="h-24 glass-card animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white flex items-center gap-3">
            <Activity className="text-neon-cyan" size={32} />
            System <span className="text-neon-cyan">Diagnostics</span>
          </h1>
          <p className="text-gray-400 mt-1">Live health monitoring of all critical bot components</p>
        </div>
        <button
          onClick={() => { setLoading(true); fetchDiagnostics(); }}
          className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/30 hover:bg-neon-cyan/20 transition-all"
        >
          <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          Run Check
        </button>
      </div>

      {error ? (
        <div className="glass-card border-neon-red/30 p-4 flex items-center gap-3 bg-neon-red/5">
          <XCircle className="text-neon-red" size={24} />
          <span className="text-neon-red font-medium">{error}</span>
        </div>
      ) : (
        <>
          <div className={`glass-card p-6 border-l-4 ${data?.is_ready ? 'border-l-neon-green bg-neon-green/5' : 'border-l-neon-red bg-neon-red/5'}`}>
            <h2 className={`text-xl font-bold ${data?.is_ready ? 'text-neon-green' : 'text-neon-red'}`}>
              {data?.overall_status}
            </h2>
            <p className="text-sm text-gray-400 mt-1">Last checked: {new Date(data?.timestamp * 1000).toLocaleTimeString()}</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {checkConfigs.map(config => {
              const checkData = data?.checks[config.key] || { status: 'loading', message: 'Checking...' };
              return (
                <div key={config.key} className="glass-card p-5 hover:border-white/10 transition-colors">
                  <div className="flex items-start gap-4">
                    <div className="mt-1">
                      {getStatusIcon(checkData.status)}
                    </div>
                    <div>
                      <h3 className="font-heading font-semibold text-white">{config.title}</h3>
                      <p className="text-xs text-gray-500 mb-2">{config.desc}</p>
                      <p className={`text-sm ${
                        checkData.status === 'ok' ? 'text-neon-green/80' : 
                        checkData.status === 'warning' ? 'text-neon-yellow/80' : 'text-neon-red/80'
                      }`}>
                        {checkData.message}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
