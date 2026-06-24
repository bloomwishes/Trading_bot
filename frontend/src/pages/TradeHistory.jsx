import { useState, useEffect, useMemo, Fragment } from 'react';
import { History, Download, Filter, Calendar, TrendingUp, TrendingDown, Award, BarChart3, ChevronDown, ChevronUp } from 'lucide-react';
import { getTradeHistory, exportTrades } from '../utils/api';
import { formatINR, formatPercent, formatDate } from '../utils/formatters';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

export default function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);
  const [filters, setFilters] = useState({
    pair: '',
    strategy: '',
    paper_mode: '',
    date_from: '',
    date_to: '',
  });
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.pair) params.pair = filters.pair;
      if (filters.strategy) params.strategy = filters.strategy;
      if (filters.paper_mode !== '') params.paper_mode = filters.paper_mode === 'true';
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
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

  // Cumulative P&L chart data
  const chartData = useMemo(() => {
    let cumPnl = 0;
    return trades
      .sort((a, b) => new Date(a.closed_at || a.created_at) - new Date(b.closed_at || b.created_at))
      .map((t, i) => {
        cumPnl += (t.pnl || 0);
        return {
          index: i + 1,
          date: new Date(t.closed_at || t.created_at).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }),
          pnl: cumPnl,
        };
      });
  }, [trades]);

  // Pie chart data
  const pieData = useMemo(() => [
    { name: 'Wins', value: stats.wins, color: '#34d399' },
    { name: 'Losses', value: stats.losses, color: '#fb7185' },
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
        <div className="flex items-center gap-3">
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
                    stroke="#22d3ee"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: '#22d3ee', stroke: '#0b0e14', strokeWidth: 2 }}
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
        <div className="p-4 border-b border-neon-cyan/10">
          <h3 className="text-lg font-heading text-white">All Closed Trades</h3>
        </div>
        {loading ? (
          <div className="p-8 space-y-3">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="h-12 bg-cyber-surface/50 rounded animate-pulse" />
            ))}
          </div>
        ) : trades.length === 0 ? (
          <div className="p-12 text-center text-gray-500">
            <History size={32} className="mx-auto mb-3 opacity-50" />
            <p>No trades found matching your filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
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
                {trades.map(trade => {
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
        )}
      </div>
    </div>
  );
}
