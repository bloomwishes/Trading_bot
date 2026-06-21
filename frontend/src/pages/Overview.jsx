import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import {
  Wallet,
  TrendingUp,
  Activity,
  Target,
  Play,
  Square,
  Zap,
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
import { getStatus, startBot, stopBot, getPortfolioSnapshots, getOpportunities } from '../utils/api';
import { formatINR, formatPercent, getChangeColor, formatDate, formatPair } from '../utils/formatters';

/**
 * Stat card component for the overview dashboard
 */
function StatCard({ icon: Icon, label, children, color = 'neon-cyan', delay = 0 }) {
  const colorMap = {
    'neon-cyan': {
      iconBg: 'bg-neon-cyan/10',
      iconColor: 'text-neon-cyan',
      border: 'hover:border-neon-cyan/30',
      glow: 'hover:shadow-[0_0_30px_rgba(0,240,255,0.1)]',
    },
    'neon-green': {
      iconBg: 'bg-neon-green/10',
      iconColor: 'text-neon-green',
      border: 'hover:border-neon-green/30',
      glow: 'hover:shadow-[0_0_30px_rgba(0,255,136,0.1)]',
    },
    'neon-magenta': {
      iconBg: 'bg-neon-magenta/10',
      iconColor: 'text-neon-magenta',
      border: 'hover:border-neon-magenta/30',
      glow: 'hover:shadow-[0_0_30px_rgba(255,0,229,0.1)]',
    },
    'neon-yellow': {
      iconBg: 'bg-neon-yellow/10',
      iconColor: 'text-neon-yellow',
      border: 'hover:border-neon-yellow/30',
      glow: 'hover:shadow-[0_0_30px_rgba(255,214,0,0.1)]',
    },
  };
  const c = colorMap[color] || colorMap['neon-cyan'];

  return (
    <div
      className={`glass-card p-5 transition-all duration-300 ${c.border} ${c.glow} hover:-translate-y-1 animate-slide-in`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between mb-3">
        <div
          className={`w-10 h-10 rounded-lg ${c.iconBg} flex items-center justify-center`}
        >
          <Icon className={`w-5 h-5 ${c.iconColor}`} />
        </div>
      </div>
      <p className="text-xs text-gray-500 uppercase tracking-wider font-heading mb-1">
        {label}
      </p>
      <div className="text-2xl font-bold font-mono text-white">{children}</div>
    </div>
  );
}

/**
 * Custom tooltip for the portfolio chart
 */
function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card px-3 py-2 text-xs">
      <p className="text-gray-400">{payload[0]?.payload?.time}</p>
      <p className="text-neon-cyan font-mono font-semibold">
        {formatINR(payload[0]?.value)}
      </p>
    </div>
  );
}

export default function Overview() {
  const { status, refetchStatus } = useOutletContext();
  const [snapshots, setSnapshots] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [snapRes, oppRes] = await Promise.allSettled([
        getPortfolioSnapshots(),
        getOpportunities(),
      ]);
      if (snapRes.status === 'fulfilled') {
        setSnapshots(snapRes.value.data?.snapshots || snapRes.value.data || []);
      }
      if (oppRes.status === 'fulfilled') {
        setOpportunities(oppRes.value.data?.opportunities || oppRes.value.data || []);
      }
    } catch {
      // Silently fail
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleStartBot = async () => {
    setActionLoading(true);
    try {
      await startBot();
      await refetchStatus();
    } catch (err) {
      console.error('Failed to start bot:', err);
    }
    setActionLoading(false);
  };

  const handleStopBot = async () => {
    setActionLoading(true);
    try {
      await stopBot();
      await refetchStatus();
    } catch (err) {
      console.error('Failed to stop bot:', err);
    }
    setActionLoading(false);
  };

  // Derived values from backend API response
  const portfolioValue = status?.portfolio?.total_value_inr || 0;
  const todayPnl = status?.portfolio?.today_pnl || 0;
  const todayPnlPct = status?.portfolio?.today_pnl_pct || 0;
  const activeTrades = status?.portfolio?.active_trades || 0;
  const winRate = status?.portfolio?.win_rate_pct || 0;
  const isRunning = status?.running === true;

  // Format chart data
  const chartData = snapshots.slice(-48).map((snap) => ({
    time: formatDate(snap.timestamp || snap.time),
    value: snap.total_value || snap.portfolio_value || snap.value || 0,
  }));

  // Recent signals
  const recentSignals = (opportunities || []).slice(0, 5);

  const { text: pnlPctText, colorClass: pnlColor } = formatPercent(todayPnlPct);

  return (
    <div className="space-y-6">
      {/* Page title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-heading font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time trading overview</p>
        </div>

        {/* Start/Stop buttons */}
        <div className="flex items-center gap-3">
          {isRunning ? (
            <button
              onClick={handleStopBot}
              disabled={actionLoading}
              className="btn-danger flex items-center gap-2 text-sm"
            >
              <Square className="w-4 h-4" />
              {actionLoading ? 'Stopping...' : 'Stop Bot'}
            </button>
          ) : (
            <button
              onClick={handleStartBot}
              disabled={actionLoading}
              className="btn-success flex items-center gap-2 text-sm"
            >
              <Play className="w-4 h-4" />
              {actionLoading ? 'Starting...' : 'Start Bot'}
            </button>
          )}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Wallet} label="Portfolio Value" color="neon-cyan" delay={0}>
          <AnimatedNumber value={portfolioValue} prefix="₹" decimals={2} />
        </StatCard>

        <StatCard icon={TrendingUp} label="Today's P&L" color="neon-green" delay={50}>
          <div className="flex items-baseline gap-2">
            <AnimatedNumber value={todayPnl} prefix="₹" decimals={2} colorize />
            <span className={`text-sm ${pnlColor}`}>{pnlPctText}</span>
          </div>
        </StatCard>

        <StatCard icon={Activity} label="Active Trades" color="neon-magenta" delay={100}>
          <AnimatedNumber value={activeTrades} decimals={0} />
        </StatCard>

        <StatCard icon={Target} label="Win Rate" color="neon-yellow" delay={150}>
          <AnimatedNumber value={winRate} suffix="%" decimals={1} />
        </StatCard>
      </div>

      {/* Charts & Signals row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Portfolio Chart */}
        <div className="lg:col-span-2 glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading font-semibold text-white text-sm uppercase tracking-wider">
              Portfolio Performance
            </h2>
            <span className="text-xs text-gray-500">Last 24h</span>
          </div>
          <div className="h-[250px]">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00f0ff" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#00f0ff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="time"
                    hide
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    hide
                    domain={['dataMin - 100', 'dataMax + 100']}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#00f0ff"
                    strokeWidth={2}
                    fill="url(#portfolioGradient)"
                    dot={false}
                    activeDot={{
                      r: 4,
                      fill: '#00f0ff',
                      stroke: '#00f0ff',
                      strokeWidth: 2,
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-600">
                <div className="text-center">
                  <Activity className="w-10 h-10 mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No chart data available</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Recent Signals */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading font-semibold text-white text-sm uppercase tracking-wider">
              Recent Signals
            </h2>
            <Zap className="w-4 h-4 text-neon-yellow" />
          </div>
          <div className="space-y-3">
            {recentSignals.length > 0 ? (
              recentSignals.map((signal, index) => {
                const score = signal.score || signal.strength || 0;
                const scoreColor =
                  score >= 70
                    ? 'text-neon-green'
                    : score >= 40
                    ? 'text-neon-yellow'
                    : 'text-neon-red';

                return (
                  <div
                    key={index}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] transition-colors animate-slide-in"
                    style={{ animationDelay: `${index * 60}ms` }}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-1.5 h-8 rounded-full ${
                          score >= 70
                            ? 'bg-neon-green'
                            : score >= 40
                            ? 'bg-neon-yellow'
                            : 'bg-neon-red'
                        }`}
                      />
                      <div>
                        <p className="text-sm font-mono font-semibold text-white">
                          {formatPair(signal.pair || signal.symbol)}
                        </p>
                        <p className="text-[10px] text-gray-500 uppercase tracking-wider">
                          {signal.strategy || signal.signal_type || 'Signal'}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-bold font-mono ${scoreColor}`}>
                        {score}
                      </p>
                      <p className="text-[10px] text-gray-600">score</p>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-8 text-gray-600">
                <Zap className="w-8 h-8 mx-auto mb-2 opacity-20" />
                <p className="text-sm">No recent signals</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
