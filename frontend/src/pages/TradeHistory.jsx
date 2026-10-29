import { useState, useEffect, useMemo, Fragment } from 'react';
import { useOutletContext } from 'react-router-dom';
import { History, Download, Filter, Calendar, TrendingUp, TrendingDown, Award, BarChart3, ChevronDown, ChevronUp, Brain, Zap, CheckCircle2, Loader2, RotateCcw } from 'lucide-react';
import { getTradeHistory, exportTrades, trainNeuralNetworkOnHistory } from '../utils/api';
import ResetPaperModal from '../components/ResetPaperModal';
import { formatINR, formatPercent, formatDate, parseDate } from '../utils/formatters';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

export default function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);
  const [trainingNN, setTrainingNN] = useState(false);
  const [trainingResult, setTrainingResult] = useState(null);
  const [filters, setFilters] = useState({
    pair: '',
    strategy: '',
    paper_mode: '',
    date_from: '',
    date_to: '',
  });
  const [pageSize, setPageSize] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);

  const outletContext = useOutletContext();
  const currentMode = outletContext?.status?.mode || 'paper';
  const refetchStatus = outletContext?.refetchStatus;
  const refetchPortfolio = outletContext?.refetchPortfolio;

  useEffect(() => {
    fetchHistory();
  }, [pageSize]);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.pair) params.pair = filters.pair;
      if (filters.strategy) params.strategy = filters.strategy;
      if (filters.paper_mode !== '') params.paper_mode = filters.paper_mode === 'true';
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      params.limit = pageSize === 'all' ? 0 : Number(pageSize);
      const res = await getTradeHistory(params);
      setTrades(res.data || []);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    try {
      const res = await exportTrades();
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trades_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  const handleTrainNeuralNetwork = async () => {
    setTrainingNN(true);
    setTrainingResult(null);
    try {
      const res = await trainNeuralNetworkOnHistory({ epochs: 35 });
      setTrainingResult(res.data?.metrics || res.data);
    } catch (err) {
      console.error('Failed to train neural network:', err);
      alert('Neural network training failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setTrainingNN(false);
    }
  };

  // Sort trades with newest on top (descending by closed_at or created_at)
  const displayTrades = useMemo(() => {
    return [...trades].sort((a, b) => {
      const da = parseDate(a.closed_at || a.created_at)?.getTime() || 0;
      const db = parseDate(b.closed_at || b.created_at)?.getTime() || 0;
      return db - da;
    });
  }, [trades]);

  // Stats calculations
  const stats = useMemo(() => {
    if (!trades.length) return { total: 0, wins: 0, losses: 0, winRate: 0, avgProfit: 0, totalPnl: 0, maxDrawdown: 0 };
    const wins = trades.filter(t => (t.pnl || 0) > 0).length;
    const losses = trades.filter(t => (t.pnl || 0) <= 0).length;
    const totalPnl = trades.reduce((s, t) => s + (t.pnl || 0), 0);
    const avgProfit = totalPnl / trades.length;
    
    // Calculate max drawdown
    let peak = 0, maxDd = 0, cumPnl = 0;
    trades.forEach(t => {
      cumPnl += (t.pnl || 0);
      if (cumPnl > peak) peak = cumPnl;
      const dd = peak - cumPnl;
      if (dd > maxDd) maxDd = dd;
    });

    return {
      total: trades.length,
      wins,
      losses,
      winRate: trades.length ? (wins / trades.length * 100) : 0,
      avgProfit,
      totalPnl,
      maxDrawdown: maxDd,
    };
  }, [trades]);

  // Cumulative P&L chart data (must be chronologically ascending for the timeline chart)
  const chartData = useMemo(() => {
    let cumPnl = 0;
    return [...trades]
      .sort((a, b) => {
        const da = parseDate(a.closed_at || a.created_at)?.getTime() || 0;
        const db = parseDate(b.closed_at || b.created_at)?.getTime() || 0;
        return da - db;
      })
      .map((t, i) => {
        cumPnl += (t.pnl || 0);
        const parsed = parseDate(t.closed_at || t.created_at);
        return {
          index: i + 1,
          date: parsed ? parsed.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }) : '—',
          pnl: cumPnl,
        };
      });
  }, [trades]);

  // Pie chart data
  const pieData = useMemo(() => [
    { name: 'Wins', value: stats.wins, color: '#00ff88' },
    { name: 'Losses', value: stats.losses, color: '#ff3366' },
  ], [stats]);

  const pairs = [...new Set(trades.map(t => t.pair))];
  const strategies = [...new Set(trades.map(t => t.strategy))];

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass-card p-3 border border-neon-cyan/20">
          <p className="text-xs text-gray-400">Trade #{payload[0].payload.index}</p>
          <p className={`text-sm font-bold font-mono ${payload[0].value >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
            {formatINR(payload[0].value)}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white">
            Trade <span className="text-neon-cyan">History</span>
          </h1>
          <p className="text-gray-400 mt-1">Review past trades and performance metrics</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {currentMode === 'paper' && (
            <button
              onClick={() => setShowResetModal(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-neon-purple/15 border border-neon-purple/50 
                         text-neon-purple hover:bg-neon-purple/25 transition-all duration-300
                         hover:shadow-[0_0_15px_rgba(180,0,255,0.3)] font-medium text-sm"
              title="Reset Paper Account: Train AI on history, close open trades, purge history, and reset capital"
            >
              <RotateCcw size={16} />
              <span>Reset Paper &amp; Train</span>
            </button>
          )}
          <button
            onClick={handleTrainNeuralNetwork}
            disabled={trainingNN || trades.length === 0}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-neon-cyan/10 border border-neon-cyan/40 
                       text-neon-cyan hover:bg-neon-cyan/20 transition-all duration-300
                       hover:shadow-[0_0_15px_rgba(0,240,255,0.25)] disabled:opacity-50"
            title="Train Neural Network on this trade history"
          >
            {trainingNN ? (
              <>
                <Loader2 size={16} className="animate-spin text-neon-cyan" />
                <span>Training Neural Net...</span>
              </>
            ) : (
              <>
                <Brain size={16} className="text-neon-cyan" />
                <span>Train Neural Net on History</span>
              </>
            )}
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-all duration-300
              ${showFilters 
                ? 'bg-neon-cyan/10 border-neon-cyan/40 text-neon-cyan' 
                : 'bg-cyber-card border-gray-700 text-gray-400 hover:border-neon-cyan/30'}`}
          >
            <Filter size={16} />
            Filters
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-neon-green/10 border border-neon-green/30 
                       text-neon-green hover:bg-neon-green/20 transition-all duration-300
                       hover:shadow-[0_0_15px_rgba(0,255,136,0.2)]"
          >
            <Download size={16} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Neural Network Training Success Banner */}
      {trainingResult && (
        <div className="glass-card p-4 border border-neon-cyan/40 bg-neon-cyan/5 rounded-xl flex items-center justify-between flex-wrap gap-3 animate-fade-in shadow-[0_0_20px_rgba(0,240,255,0.15)]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-neon-cyan/20 border border-neon-cyan/40 flex items-center justify-center text-neon-cyan flex-shrink-0">
              <CheckCircle2 size={22} />
            </div>
            <div>
              <p className="text-sm font-bold text-white flex items-center gap-2">
                <span>Neural Network Calibrated on {trainingResult.total_trades || trades.length} Historical Trades</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40">
                  Weights Saved
                </span>
              </p>
              <p className="text-xs text-gray-300 mt-1">
                Processed <span className="text-neon-green font-semibold">{trainingResult.wins} Wins</span> &amp; <span className="text-neon-red font-semibold">{trainingResult.losses} Losses</span> ({trainingResult.win_rate_pct}% win rate) over {trainingResult.epochs} epochs • Final Loss: <span className="font-mono text-neon-cyan">{trainingResult.loss}</span> • Accuracy: <span className="font-mono text-neon-green">{(trainingResult.accuracy * 100).toFixed(1)}%</span> • Synaptic weights updated to protect capital!
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="/neural"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-neon-cyan text-black hover:bg-neon-cyan/80 transition-all shadow-[0_0_10px_rgba(0,240,255,0.4)]"
            >
              View Brain Activations →
            </a>
            <button
              onClick={() => setTrainingResult(null)}
              className="text-xs text-gray-400 hover:text-white px-2 py-1"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Filters Panel */}
      {showFilters && (
        <div className="glass-card p-6 animate-slide-in">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <label className="text-xs text-gray-500 uppercase mb-1 block">Pair</label>
              <select
                value={filters.pair}
                onChange={e => setFilters(p => ({ ...p, pair: e.target.value }))}
                className="w-full bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                           focus:border-neon-cyan/50 focus:outline-none transition-colors"
              >
                <option value="">All Pairs</option>
                {pairs.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 uppercase mb-1 block">Strategy</label>
              <select
                value={filters.strategy}
                onChange={e => setFilters(p => ({ ...p, strategy: e.target.value }))}
                className="w-full bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                           focus:border-neon-cyan/50 focus:outline-none transition-colors"
              >
                <option value="">All Strategies</option>
                {strategies.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 uppercase mb-1 block">Mode</label>
              <select
                value={filters.paper_mode}
                onChange={e => setFilters(p => ({ ...p, paper_mode: e.target.value }))}
                className="w-full bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                           focus:border-neon-cyan/50 focus:outline-none transition-colors"
              >
                <option value="">All</option>
                <option value="true">Paper</option>
                <option value="false">Live</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 uppercase mb-1 block">From</label>
              <input
                type="date"
                value={filters.date_from}
                onChange={e => setFilters(p => ({ ...p, date_from: e.target.value }))}
                className="w-full bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                           focus:border-neon-cyan/50 focus:outline-none transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 uppercase mb-1 block">To</label>
              <input
                type="date"
                value={filters.date_to}
                onChange={e => setFilters(p => ({ ...p, date_to: e.target.value }))}
                className="w-full bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-sm text-white
                           focus:border-neon-cyan/50 focus:outline-none transition-colors"
              />
            </div>
          </div>
          <div className="mt-4 flex gap-3">
            <button
              onClick={fetchHistory}
              className="px-4 py-2 rounded-lg bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30 
                         hover:bg-neon-cyan/30 text-sm font-medium transition-all"
            >
              Apply Filters
            </button>
            <button
              onClick={() => { setFilters({ pair: '', strategy: '', paper_mode: '', date_from: '', date_to: '' }); }}
              className="px-4 py-2 rounded-lg bg-cyber-surface text-gray-400 border border-gray-700 
                         hover:border-gray-500 text-sm transition-all"
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Trades', value: stats.total, icon: BarChart3, color: 'neon-cyan' },
          { label: 'Win Rate', value: `${stats.winRate.toFixed(1)}%`, icon: Award, color: 'neon-green' },
          { label: 'Avg Profit', value: formatINR(stats.avgProfit), icon: stats.avgProfit >= 0 ? TrendingUp : TrendingDown, color: stats.avgProfit >= 0 ? 'neon-green' : 'neon-red' },
          { label: 'Max Drawdown', value: formatINR(stats.maxDrawdown), icon: TrendingDown, color: 'neon-red' },
        ].map((stat, i) => (
          <div key={i} className="glass-card p-4 group hover:border-neon-cyan/30 transition-all duration-300">
            <div className="flex items-center gap-2 mb-2">
              <stat.icon size={16} className={`text-${stat.color}`} />
              <span className="text-xs text-gray-500 uppercase">{stat.label}</span>
            </div>
            <div className={`text-2xl font-bold font-mono text-${stat.color}`}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      {trades.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Cumulative P&L Chart */}
          <div className="lg:col-span-2 glass-card p-6">
            <h3 className="text-lg font-heading text-white mb-4">Cumulative P&L</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={{ stroke: 'rgba(255,255,255,0.1)' }} />
                  <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                    tickFormatter={v => `₹${(v / 1000).toFixed(1)}k`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="pnl"
                    stroke="#00f0ff"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: '#00f0ff', stroke: '#0a0a0f', strokeWidth: 2 }}
                    filter="drop-shadow(0 0 6px rgba(0, 240, 255, 0.5))"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Win/Loss Pie Chart */}
          <div className="glass-card p-6">
            <h3 className="text-lg font-heading text-white mb-4">Win / Loss Ratio</h3>
            <div className="h-64 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    stroke="none"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} opacity={0.8} />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="glass-card p-2 border border-neon-cyan/20">
                            <p className="text-sm text-white">{payload[0].name}: {payload[0].value}</p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-center gap-6 mt-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-neon-green" />
                <span className="text-sm text-gray-400">Wins ({stats.wins})</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-neon-red" />
                <span className="text-sm text-gray-400">Losses ({stats.losses})</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trade List */}
      <div className="glass-card overflow-hidden">
        <div className="p-4 border-b border-neon-cyan/10 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-heading text-white">Closed Trade History</h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20">
                Newest First
              </span>
            </div>
            <p className="text-xs text-gray-400">
              Showing <span className="text-neon-cyan font-semibold">{displayTrades.length}</span> recorded trades (most recent on top)
            </p>
          </div>
          <div className="flex items-center gap-1 bg-cyber-surface/60 p-1 rounded-lg border border-white/5 text-xs">
            <span className="text-gray-400 px-2">Show:</span>
            {['50', '100', '250', 'all'].map((size) => (
              <button
                key={size}
                onClick={() => setPageSize(size)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                  pageSize === size
                    ? 'bg-neon-cyan text-black font-bold shadow-[0_0_10px_rgba(0,240,255,0.4)]'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {size === 'all' ? 'All' : size}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="p-8 space-y-3">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="h-12 bg-cyber-surface/50 rounded animate-pulse" />
            ))}
          </div>
        ) : displayTrades.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <History size={32} className="mx-auto mb-3 opacity-50" />
            <p>No trades found matching your filters</p>
          </div>
        ) : (
          <>
            {/* MOBILE ONLY VIEW: Vertical Cards without horizontal scrolling (Newest First) */}
            <div className="block md:hidden p-3 space-y-3">
              {displayTrades.map(trade => {
                const isExpanded = expandedRow === trade.id;
                const isProfit = (trade.pnl || 0) >= 0;
                return (
                  <div
                    key={trade.id}
                    className="p-3.5 rounded-lg bg-cyber-surface/30 border border-cyber-surface/60 space-y-2.5 transition-all"
                  >
                    {/* Top Row: Date, Pair, Side, Strategy */}
                    <div className="flex items-center justify-between border-b border-cyber-surface/50 pb-2">
                      <div>
                        <span className="font-bold text-base text-white">{trade.pair}</span>
                        <span className="text-[11px] text-gray-400 ml-2 font-mono">
                          {formatDate(trade.closed_at || trade.created_at)}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${trade.side === 'BUY' ? 'bg-neon-green/10 text-neon-green border border-neon-green/30' : 'bg-neon-red/10 text-neon-red border border-neon-red/30'}`}>
                          {trade.side}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyber-surface text-gray-300">
                          {trade.strategy}
                        </span>
                      </div>
                    </div>

                    {/* Realized P&L Banner */}
                    <div className={`p-2 rounded flex items-center justify-between border ${isProfit ? 'bg-neon-green/10 border-neon-green/25' : 'bg-neon-red/10 border-neon-red/25'}`}>
                      <span className="text-xs uppercase font-heading text-gray-300">Realized P&L</span>
                      <div className="text-right">
                        <span className={`font-mono font-bold text-sm ${isProfit ? 'text-neon-green' : 'text-neon-red'}`}>
                          {isProfit ? '+' : ''}{formatINR(trade.pnl || 0)}
                        </span>
                        {trade.pnl_pct !== undefined && (
                          <span className={`text-xs font-mono ml-1.5 ${isProfit ? 'text-neon-green/80' : 'text-neon-red/80'}`}>
                            ({isProfit ? '+' : ''}{trade.pnl_pct?.toFixed(2)}%)
                          </span>
                        )}
                      </div>
                    </div>

                    {/* 2x2 Details Grid */}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="p-2 rounded bg-black/20">
                        <span className="text-gray-400 block mb-0.5">Entry</span>
                        <span className="font-mono text-gray-200">{formatINR(trade.entry_price)}</span>
                      </div>
                      <div className="p-2 rounded bg-black/20">
                        <span className="text-gray-400 block mb-0.5">Exit</span>
                        <span className="font-mono text-gray-200">{formatINR(trade.exit_price)}</span>
                      </div>
                      <div className="p-2 rounded bg-black/20">
                        <span className="text-gray-400 block mb-0.5">Quantity</span>
                        <span className="font-mono text-gray-300">{trade.quantity?.toFixed(6)}</span>
                      </div>
                      <div className="p-2 rounded bg-black/20">
                        <span className="text-gray-400 block mb-0.5">Mode</span>
                        <span className={`text-[11px] font-semibold ${trade.paper_mode ? 'text-neon-cyan' : 'text-neon-magenta'}`}>
                          {trade.paper_mode ? 'Paper' : 'Live'}
                        </span>
                      </div>
                    </div>

                    {/* Expand Details Trigger */}
                    <button
                      onClick={() => setExpandedRow(isExpanded ? null : trade.id)}
                      className="w-full pt-1 text-xs text-gray-400 hover:text-neon-cyan flex items-center justify-center gap-1 transition-colors"
                    >
                      <span>{isExpanded ? 'Hide Details' : 'View Reasons'}</span>
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>

                    {/* Expandable reasons */}
                    {isExpanded && (
                      <div className="pt-2 border-t border-cyber-surface/40 space-y-2 text-xs">
                        <div>
                          <span className="text-neon-cyan font-semibold block mb-0.5">Entry Reason</span>
                          <p className="text-gray-300 bg-black/30 p-2 rounded">
                            {trade.entry_reason || 'Manual execution or standard indicator trigger.'}
                          </p>
                        </div>
                        <div>
                          <span className="text-neon-red font-semibold block mb-0.5">Exit Reason</span>
                          <p className="text-gray-300 bg-black/30 p-2 rounded">
                            {trade.exit_reason || 'Target achieved or exit signal triggered.'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* DESKTOP VIEW: Full Data Table (hidden on mobile, visible on md+) */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-cyber-surface">
                    <th className="text-left p-3 text-xs font-medium text-gray-500 uppercase">Date</th>
                    <th className="text-left p-3 text-xs font-medium text-gray-500 uppercase">Pair</th>
                    <th className="text-left p-3 text-xs font-medium text-gray-500 uppercase">Strategy</th>
                    <th className="text-left p-3 text-xs font-medium text-gray-500 uppercase">Side</th>
                    <th className="text-right p-3 text-xs font-medium text-gray-500 uppercase">Entry</th>
                    <th className="text-right p-3 text-xs font-medium text-gray-500 uppercase">Exit</th>
                    <th className="text-right p-3 text-xs font-medium text-gray-500 uppercase">Qty</th>
                    <th className="text-right p-3 text-xs font-medium text-gray-500 uppercase">P&L</th>
                    <th className="text-center p-3 text-xs font-medium text-gray-500 uppercase">Mode</th>
                    <th className="text-center p-3 text-xs font-medium text-gray-500 uppercase">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-cyber-surface/30">
                  {displayTrades.map(trade => {
                    const isExpanded = expandedRow === trade.id;
                    return (
                      <Fragment key={trade.id}>
                        <tr 
                          className="hover:bg-cyber-surface/20 transition-colors cursor-pointer"
                          onClick={() => setExpandedRow(isExpanded ? null : trade.id)}
                        >
                          <td className="p-3 text-sm text-gray-400">{formatDate(trade.closed_at || trade.created_at)}</td>
                          <td className="p-3 text-sm font-semibold text-white">{trade.pair}</td>
                          <td className="p-3">
                            <span className="text-xs px-2 py-0.5 rounded bg-cyber-surface text-gray-300">{trade.strategy}</span>
                          </td>
                          <td className="p-3">
                            <span className={`text-sm font-semibold ${trade.side === 'BUY' ? 'text-neon-green' : 'text-neon-red'}`}>
                              {trade.side}
                            </span>
                          </td>
                          <td className="p-3 text-right text-sm text-gray-300 font-mono">{formatINR(trade.entry_price)}</td>
                          <td className="p-3 text-right text-sm text-gray-300 font-mono">{formatINR(trade.exit_price)}</td>
                          <td className="p-3 text-right text-sm text-gray-400 font-mono">{trade.quantity?.toFixed(6)}</td>
                          <td className="p-3 text-right">
                            <span className={`text-sm font-bold font-mono ${(trade.pnl || 0) >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
                              {(trade.pnl || 0) >= 0 ? '+' : ''}{formatINR(trade.pnl || 0)}
                            </span>
                          </td>
                          <td className="p-3 text-center">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${trade.paper_mode 
                              ? 'bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20' 
                              : 'bg-neon-magenta/10 text-neon-magenta border border-neon-magenta/20'}`}>
                              {trade.paper_mode ? 'Paper' : 'Live'}
                            </span>
                          </td>
                          <td className="p-3 text-center">
                            {isExpanded ? (
                              <ChevronUp size={16} className="mx-auto text-neon-cyan" />
                            ) : (
                              <ChevronDown size={16} className="mx-auto text-gray-500" />
                            )}
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="bg-cyber-surface/10">
                            <td colSpan="10" className="p-4 border-t border-b border-cyber-surface/20">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-slide-in">
                                <div>
                                  <h4 className="text-xs text-neon-cyan uppercase font-bold mb-1 tracking-wider">Entry Reason</h4>
                                  <p className="text-sm text-gray-300 bg-cyber-bg/40 p-3 rounded border border-gray-800/50">
                                    {trade.entry_reason || 'Manual execution or standard indicator trigger.'}
                                  </p>
                                </div>
                                <div>
                                  <h4 className="text-xs text-neon-red uppercase font-bold mb-1 tracking-wider">Exit Reason</h4>
                                  <p className="text-sm text-gray-300 bg-cyber-bg/40 p-3 rounded border border-gray-800/50">
                                    {trade.exit_reason || 'Target achieved or exit signal triggered.'}
                                  </p>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      <ResetPaperModal
        isOpen={showResetModal}
        onClose={() => setShowResetModal(false)}
        onSuccess={() => {
          fetchHistory();
          refetchStatus?.();
          refetchPortfolio?.();
        }}
      />
    </div>
  );
}
