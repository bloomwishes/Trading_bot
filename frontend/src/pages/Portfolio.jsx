import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Wallet,
  Coins,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ShieldCheck,
  RotateCcw,
  Banknote,
  PieChart,
  Layers,
  Search,
  ExternalLink,
  Lock,
  ArrowUpRight,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import AnimatedNumber from '../components/AnimatedNumber';
import ResetPaperModal from '../components/ResetPaperModal';
import { getPortfolioCurrent, getHoldings, getPortfolioSnapshots } from '../utils/api';
import { formatINR, formatPercent, formatDate, formatPair } from '../utils/formatters';

// Color palette for asset allocation visualizer
const ASSET_COLORS = [
  { bg: 'bg-[#00f0ff]', text: 'text-[#00f0ff]', hex: '#00f0ff', border: 'border-[#00f0ff]/40' },
  { bg: 'bg-[#ff00e5]', text: 'text-[#ff00e5]', hex: '#ff00e5', border: 'border-[#ff00e5]/40' },
  { bg: 'bg-[#00ff88]', text: 'text-[#00ff88]', hex: '#00ff88', border: 'border-[#00ff88]/40' },
  { bg: 'bg-[#ffd600]', text: 'text-[#ffd600]', hex: '#ffd600', border: 'border-[#ffd600]/40' },
  { bg: 'bg-[#ff5500]', text: 'text-[#ff5500]', hex: '#ff5500', border: 'border-[#ff5500]/40' },
  { bg: 'bg-[#b400ff]', text: 'text-[#b400ff]', hex: '#b400ff', border: 'border-[#b400ff]/40' },
  { bg: 'bg-[#3b82f6]', text: 'text-[#3b82f6]', hex: '#3b82f6', border: 'border-[#3b82f6]/40' },
];

export default function Portfolio() {
  const { status, refetchStatus, refetchPortfolio } = useOutletContext();
  const navigate = useNavigate();

  const [portfolioData, setPortfolioData] = useState(null);
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [searchQuery, setSearchQuery] = useState('');
  const [assetFilter, setAssetFilter] = useState('all'); // 'all' | 'crypto' | 'cash'
  const [chartTimeframe, setChartTimeframe] = useState('all'); // '24h' | '7d' | '30d' | 'all'
  const [resetModalOpen, setResetModalOpen] = useState(false);

  const mode = status?.mode || portfolioData?.mode || 'paper';
  const isLive = mode === 'live';

  // Fetch portfolio breakdown & holdings
  const loadPortfolio = useCallback(async () => {
    try {
      const res = await getPortfolioCurrent();
      setPortfolioData(res.data);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to load portfolio current:', err);
    }
  }, []);

  // Fetch historical snapshots for chart
  const loadSnapshots = useCallback(async () => {
    try {
      const res = await getPortfolioSnapshots({ limit: 300 });
      setSnapshots(res.data || []);
    } catch (err) {
      console.error('Failed to load portfolio snapshots:', err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    async function init() {
      setLoading(true);
      await Promise.all([loadPortfolio(), loadSnapshots()]);
      setLoading(false);
    }
    init();

    const interval = setInterval(() => {
      loadPortfolio();
    }, 10000);

    return () => clearInterval(interval);
  }, [loadPortfolio, loadSnapshots]);

  // Handle manual refresh
  const handleManualRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadPortfolio(), loadSnapshots(), refetchStatus?.(), refetchPortfolio?.()]);
    setTimeout(() => setRefreshing(false), 600);
  };

  // Derive metrics
  const totalValue = portfolioData?.total_value_inr ?? 0;
  const cashBalance = portfolioData?.cash_balance_inr ?? 0;
  const positionsValue = portfolioData?.positions_value_inr ?? 0;
  const holdings = portfolioData?.holdings || [];
  const positions = portfolioData?.positions || [];

  // Crypto holdings value
  const cryptoHoldingsValue = holdings
    .filter((h) => h.currency !== 'INR')
    .reduce((sum, h) => sum + (h.value_inr || 0), 0);

  // Filtered holdings list
  const filteredHoldings = useMemo(() => {
    return holdings.filter((item) => {
      const isCash = item.currency === 'INR';
      if (assetFilter === 'crypto' && isCash) return false;
      if (assetFilter === 'cash' && !isCash) return false;

      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        item.currency.toLowerCase().includes(q) ||
        (isCash ? 'fiat cash' : 'spot crypto').includes(q)
      );
    });
  }, [holdings, assetFilter, searchQuery]);

  // Filter chart snapshots
  const filteredSnapshots = useMemo(() => {
    if (!snapshots || snapshots.length === 0) return [];
    if (chartTimeframe === 'all') return snapshots;

    const now = Date.now();
    const lookbacks = {
      '24h': 24 * 60 * 60 * 1000,
      '7d': 7 * 24 * 60 * 60 * 1000,
      '30d': 30 * 24 * 60 * 60 * 1000,
    };
    const cutoff = now - (lookbacks[chartTimeframe] || 0);
    return snapshots.filter((s) => new Date(s.created_at).getTime() >= cutoff);
  }, [snapshots, chartTimeframe]);

  const chartData = useMemo(() => {
    return filteredSnapshots.map((s) => ({
      time: s.created_at,
      value: s.total_value,
    }));
  }, [filteredSnapshots]);

  // Allocation distribution items
  const allocationItems = useMemo(() => {
    if (!holdings || holdings.length === 0 || totalValue <= 0) return [];
    return holdings
      .map((h, index) => {
        const pct = (h.value_inr / totalValue) * 100;
        const color = ASSET_COLORS[index % ASSET_COLORS.length];
        return {
          ...h,
          pct: Math.max(0, pct),
          color,
        };
      })
      .filter((h) => h.pct > 0.05);
  }, [holdings, totalValue]);

  return (
    <div className="space-y-6 pb-12">
      {/* Top Header / Mode Banner */}
      <div className="glass-card p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 border border-neon-cyan/20 shadow-[0_0_30px_rgba(0,240,255,0.06)] relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-neon-cyan/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-10 h-10 rounded-xl bg-neon-cyan/10 border border-neon-cyan/30 flex items-center justify-center glow-cyan">
              <Wallet className="w-5 h-5 text-neon-cyan" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="font-heading text-2xl font-bold text-white tracking-wide">
                  Portfolio & Asset Holdings
                </h1>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold tracking-wider uppercase flex items-center gap-1.5 ${
                    isLive
                      ? 'bg-neon-green/15 text-neon-green border border-neon-green/40 shadow-[0_0_12px_rgba(0,255,136,0.3)]'
                      : 'bg-neon-yellow/15 text-neon-yellow border border-neon-yellow/40 shadow-[0_0_12px_rgba(255,214,0,0.2)]'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      isLive ? 'bg-neon-green animate-pulse' : 'bg-neon-yellow'
                    }`}
                  />
                  {isLive ? 'CoinDCX Live Wallet' : 'Paper Trading Account'}
                </span>
              </div>
              <p className="text-xs text-gray-400 font-sans mt-0.5">
                {isLive
                  ? 'Real-time spot wallet balances and market valuations verified via CoinDCX API (IPv4).'
                  : 'Simulated portfolio environment with paper trading balances, open trades, and neural learning.'}
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="relative z-10 flex items-center gap-3 flex-wrap">
          <div className="text-right hidden sm:block">
            <span className="text-[10px] text-gray-400 uppercase tracking-wider block font-heading">
              Last Synchronized
            </span>
            <span className="text-xs font-mono text-gray-300">
              {formatDate(lastUpdated)}
            </span>
          </div>

          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-neon-cyan/10 hover:bg-neon-cyan/20 border border-neon-cyan/30 text-neon-cyan text-xs font-heading font-semibold transition-all hover:shadow-[0_0_15px_rgba(0,240,255,0.2)] hover:-translate-y-0.5 disabled:opacity-50"
            title="Refresh Live Balances from CoinDCX"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>{refreshing ? 'Syncing...' : 'Sync Wallet'}</span>
          </button>

          {!isLive && (
            <button
              onClick={() => setResetModalOpen(true)}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-neon-purple/15 hover:bg-neon-purple/25 border border-neon-purple/40 text-neon-purple text-xs font-heading font-semibold transition-all hover:shadow-[0_0_15px_rgba(180,0,255,0.3)] hover:-translate-y-0.5"
              title="Train neural network, close active trades, clear history, and reset capital"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset Paper Account</span>
            </button>
          )}
        </div>
      </div>

      {/* 4 Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Net Portfolio Value */}
        <div className="glass-card p-5 border-l-4 border-l-neon-cyan hover:border-neon-cyan/30 transition-all hover:-translate-y-1 shadow-[0_0_20px_rgba(0,240,255,0.05)]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase tracking-wider font-heading text-gray-400">
              Total Portfolio Equity
            </span>
            <div className="w-8 h-8 rounded-lg bg-neon-cyan/10 flex items-center justify-center text-neon-cyan">
              <Wallet className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-white mb-1">
            <AnimatedNumber value={totalValue} prefix="₹" decimals={2} />
          </div>
          <p className="text-[11px] text-gray-400">
            {isLive ? 'Spot Crypto + Cash (CoinDCX)' : 'Paper Cash + Open Positions'}
          </p>
        </div>

        {/* Spot Crypto Holdings Value */}
        <div className="glass-card p-5 border-l-4 border-l-neon-green hover:border-neon-green/30 transition-all hover:-translate-y-1 shadow-[0_0_20px_rgba(0,255,136,0.05)]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase tracking-wider font-heading text-gray-400">
              Spot Crypto Holdings
            </span>
            <div className="w-8 h-8 rounded-lg bg-neon-green/10 flex items-center justify-center text-neon-green">
              <Coins className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-neon-green mb-1">
            <AnimatedNumber value={cryptoHoldingsValue} prefix="₹" decimals={2} />
          </div>
          <p className="text-[11px] text-gray-400">
            {holdings.filter((h) => h.currency !== 'INR').length} crypto asset(s) at live rate
          </p>
        </div>

        {/* Free Cash Balance */}
        <div className="glass-card p-5 border-l-4 border-l-neon-yellow hover:border-neon-yellow/30 transition-all hover:-translate-y-1 shadow-[0_0_20px_rgba(255,214,0,0.05)]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase tracking-wider font-heading text-gray-400">
              Available Cash (INR)
            </span>
            <div className="w-8 h-8 rounded-lg bg-neon-yellow/10 flex items-center justify-center text-neon-yellow">
              <Banknote className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-neon-yellow mb-1">
            <AnimatedNumber value={cashBalance} prefix="₹" decimals={2} />
          </div>
          <p className="text-[11px] text-gray-400">
            Free unencumbered INR for trades
          </p>
        </div>

        {/* Active Open Positions Value */}
        <div className="glass-card p-5 border-l-4 border-l-neon-magenta hover:border-neon-magenta/30 transition-all hover:-translate-y-1 shadow-[0_0_20px_rgba(255,0,229,0.05)]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase tracking-wider font-heading text-gray-400">
              Active Trade Positions
            </span>
            <div className="w-8 h-8 rounded-lg bg-neon-magenta/10 flex items-center justify-center text-neon-magenta">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-mono text-white mb-1">
            <AnimatedNumber value={positionsValue} prefix="₹" decimals={2} />
          </div>
          <p className="text-[11px] text-gray-400">
            {positions.length} active bot trade position(s)
          </p>
        </div>
      </div>

      {/* Asset Allocation Breakdown Visualizer */}
      {allocationItems.length > 0 && (
        <div className="glass-card p-5 border border-white/10">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4 text-neon-cyan" />
              <h3 className="font-heading text-sm font-semibold text-white tracking-wide uppercase">
                Asset Allocation Breakdown
              </h3>
            </div>
            <span className="text-xs font-mono text-gray-400">
              {allocationItems.length} Allocations
            </span>
          </div>

          {/* Progress Stack Bar */}
          <div className="w-full h-3 rounded-full bg-white/5 overflow-hidden flex gap-0.5 p-0.5 mb-3 border border-white/10">
            {allocationItems.map((item, idx) => (
              <div
                key={idx}
                className={`h-full rounded-sm ${item.color.bg} transition-all duration-500 hover:opacity-80`}
                style={{ width: `${Math.max(2, item.pct)}%` }}
                title={`${item.currency}: ${item.pct.toFixed(1)}% (${formatINR(item.value_inr)})`}
              />
            ))}
          </div>

          {/* Allocation Badges */}
          <div className="flex flex-wrap items-center gap-2.5">
            {allocationItems.map((item, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/[0.03] border ${item.color.border}`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: item.color.hex }}
                />
                <span className="text-xs font-bold text-white font-mono">
                  {item.currency}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  {item.pct.toFixed(1)}%
                </span>
                <span className="text-xs font-mono font-medium text-gray-200">
                  ({formatINR(item.value_inr)})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CoinDCX Spot Wallet Holdings Table */}
      <div className="glass-card p-6 border border-white/10 space-y-4">
        {/* Table Controls / Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Coins className="w-5 h-5 text-neon-cyan" />
              <h2 className="font-heading text-lg font-bold text-white tracking-wide">
                {isLive ? 'CoinDCX Live Spot Holdings' : 'Simulated Account Balances'}
              </h2>
            </div>
            <p className="text-xs text-gray-400 font-sans mt-0.5">
              {isLive
                ? 'Spot cryptocurrency wallet balances retrieved directly from your CoinDCX account.'
                : 'Simulated holdings in paper trading mode.'}
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Filter Pills */}
            <div className="flex items-center bg-white/5 rounded-lg p-0.5 border border-white/10">
              <button
                onClick={() => setAssetFilter('all')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  assetFilter === 'all'
                    ? 'bg-neon-cyan/20 text-neon-cyan font-bold'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                All Assets
              </button>
              <button
                onClick={() => setAssetFilter('crypto')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  assetFilter === 'crypto'
                    ? 'bg-neon-green/20 text-neon-green font-bold'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Crypto Only
              </button>
              <button
                onClick={() => setAssetFilter('cash')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                  assetFilter === 'cash'
                    ? 'bg-neon-yellow/20 text-neon-yellow font-bold'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                INR Cash
              </button>
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search coin..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 bg-black/40 border border-white/10 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-neon-cyan/50 w-36 sm:w-44 font-sans"
              />
            </div>
          </div>
        </div>

        {/* Holdings Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-sans">
            <thead>
              <tr className="border-b border-white/10 text-[10px] font-mono uppercase text-gray-400">
                <th className="py-3 px-3">Asset</th>
                <th className="py-3 px-3 text-right">Available Qty</th>
                <th className="py-3 px-3 text-right">In Orders (Locked)</th>
                <th className="py-3 px-3 text-right">Total Balance</th>
                <th className="py-3 px-3 text-right">Market Price (INR)</th>
                <th className="py-3 px-3 text-right">Total Value (INR)</th>
                <th className="py-3 px-3 text-right">Portfolio Share</th>
                <th className="py-3 px-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono">
              {filteredHoldings.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-gray-400 font-sans">
                    {searchQuery ? 'No matching assets found.' : 'No asset holdings available.'}
                  </td>
                </tr>
              ) : (
                filteredHoldings.map((h, i) => {
                  const isCash = h.currency === 'INR';
                  const pct = totalValue > 0 ? ((h.value_inr / totalValue) * 100).toFixed(1) : 0;
                  return (
                    <tr
                      key={i}
                      className="hover:bg-white/[0.03] transition-colors group"
                    >
                      {/* Asset */}
                      <td className="py-3.5 px-3">
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs tracking-wider ${
                              isCash
                                ? 'bg-neon-yellow/20 text-neon-yellow border border-neon-yellow/30'
                                : 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30'
                            }`}
                          >
                            {h.currency.slice(0, 3)}
                          </span>
                          <div>
                            <span className="text-white font-bold block text-sm">
                              {h.currency}
                            </span>
                            <span className="text-[10px] text-gray-500 uppercase tracking-wider">
                              {isCash ? 'Fiat Currency' : 'Spot Crypto'}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Available Qty */}
                      <td className="py-3.5 px-3 text-right text-gray-200 font-semibold">
                        {h.available.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                      </td>

                      {/* In Orders / Locked */}
                      <td className="py-3.5 px-3 text-right text-gray-400">
                        {h.locked > 0 ? (
                          <span className="text-neon-yellow">
                            {h.locked.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                          </span>
                        ) : (
                          '0.00'
                        )}
                      </td>

                      {/* Total Balance */}
                      <td className="py-3.5 px-3 text-right text-white font-bold">
                        {h.total.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                      </td>

                      {/* Market Price */}
                      <td className="py-3.5 px-3 text-right text-gray-300">
                        {isCash ? '₹1.00' : formatINR(h.price_inr)}
                      </td>

                      {/* Total Value */}
                      <td className="py-3.5 px-3 text-right font-bold text-sm text-neon-cyan">
                        {formatINR(h.value_inr)}
                      </td>

                      {/* Portfolio Share */}
                      <td className="py-3.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className="h-full bg-neon-cyan rounded-full transition-all duration-300"
                              style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
                            />
                          </div>
                          <span className="text-[11px] text-gray-400 min-w-[36px]">
                            {pct}%
                          </span>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-3 text-center">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            isCash
                              ? 'bg-neon-yellow/10 text-neon-yellow border border-neon-yellow/30'
                              : 'bg-neon-green/10 text-neon-green border border-neon-green/30'
                          }`}
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          {isLive ? 'CoinDCX Synced' : 'Active'}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Active Positions / Open Bot Trades (if any) */}
      <div className="glass-card p-6 border border-white/10 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-neon-magenta" />
            <h2 className="font-heading text-lg font-bold text-white tracking-wide">
              Active Bot Positions ({positions.length})
            </h2>
          </div>
          <button
            onClick={() => navigate('/trades')}
            className="flex items-center gap-1 text-xs text-neon-cyan hover:underline font-mono"
          >
            <span>View Live Trades</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {positions.length === 0 ? (
          <div className="py-8 text-center bg-white/[0.02] rounded-xl border border-white/5">
            <ShieldCheck className="w-8 h-8 text-neon-green mx-auto mb-2 opacity-80" />
            <p className="text-sm font-heading font-medium text-gray-300">
              No Open Bot Positions
            </p>
            <p className="text-xs text-gray-500 max-w-md mx-auto mt-1 font-sans">
              All capital is safely retained in your spot wallet balances without active drawdown risk.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead>
                <tr className="border-b border-white/10 text-[10px] font-mono uppercase text-gray-400">
                  <th className="py-3 px-3">Pair</th>
                  <th className="py-3 px-3">Side</th>
                  <th className="py-3 px-3 text-right">Entry Price</th>
                  <th className="py-3 px-3 text-right">Current Price</th>
                  <th className="py-3 px-3 text-right">Quantity</th>
                  <th className="py-3 px-3 text-right">Position Value</th>
                  <th className="py-3 px-3 text-right">Unrealised PnL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-mono">
                {positions.map((pos, i) => {
                  const pnl = formatPercent(pos.unrealised_pnl_pct);
                  return (
                    <tr key={i} className="hover:bg-white/[0.03] transition-colors">
                      <td className="py-3 px-3 font-bold text-white">
                        {formatPair(pos.pair)}
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            pos.side === 'BUY'
                              ? 'bg-neon-green/20 text-neon-green'
                              : 'bg-neon-red/20 text-neon-red'
                          }`}
                        >
                          {pos.side}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right text-gray-300">
                        {formatINR(pos.entry_price)}
                      </td>
                      <td className="py-3 px-3 text-right text-gray-200">
                        {formatINR(pos.current_price)}
                      </td>
                      <td className="py-3 px-3 text-right text-gray-300">
                        {pos.quantity}
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-white">
                        {formatINR(pos.position_value_inr)}
                      </td>
                      <td className={`py-3 px-3 text-right font-bold ${pnl.colorClass}`}>
                        {formatINR(pos.unrealised_pnl_inr)} ({pnl.text})
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Historical Portfolio Growth Chart */}
      <div className="glass-card p-6 border border-white/10 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="font-heading text-lg font-bold text-white tracking-wide">
              Portfolio Growth History
            </h2>
            <p className="text-xs text-gray-400 font-sans mt-0.5">
              Historical equity valuation snapshots and account trend.
            </p>
          </div>

          <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5 border border-white/10">
            {['24h', '7d', '30d', 'all'].map((tf) => (
              <button
                key={tf}
                onClick={() => setChartTimeframe(tf)}
                className={`px-3 py-1 rounded-md text-xs font-mono uppercase transition-all ${
                  chartTimeframe === tf
                    ? 'bg-neon-cyan/20 text-neon-cyan font-bold shadow-[0_0_8px_rgba(0,240,255,0.3)]'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="h-64 w-full">
          {chartData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-gray-500 font-sans text-xs">
              Waiting for portfolio snapshots to populate...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00f0ff" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#00f0ff" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="time"
                  tickFormatter={(val) => {
                    const d = new Date(val);
                    return isNaN(d) ? '' : `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
                  }}
                  stroke="#555"
                  tick={{ fill: '#888', fontSize: 10, fontFamily: 'monospace' }}
                />
                <YAxis
                  stroke="#555"
                  tick={{ fill: '#888', fontSize: 10, fontFamily: 'monospace' }}
                  tickFormatter={(val) => `₹${val.toLocaleString()}`}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(10, 15, 29, 0.95)',
                    border: '1px solid rgba(0, 240, 255, 0.3)',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                  }}
                  formatter={(val) => [formatINR(val), 'Portfolio Equity']}
                  labelFormatter={(lbl) => formatDate(lbl)}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#00f0ff"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#portfolioGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Paper Account Reset Modal */}
      <ResetPaperModal
        isOpen={resetModalOpen}
        onClose={() => setResetModalOpen(false)}
        onSuccess={() => {
          loadPortfolio();
          loadSnapshots();
          refetchStatus?.();
        }}
      />
    </div>
  );
}
