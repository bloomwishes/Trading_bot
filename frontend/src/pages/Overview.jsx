import React, { useEffect, useState, useCallback } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Wallet,
  TrendingUp,
  Activity,
  Target,
  Play,
  Square,
  Zap,
  QrCode,
  Smartphone,
  Bot,
  Coins,
  ArrowUpRight,
  ShieldCheck,
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
import MobileQRCodeModal from '../components/MobileQRCodeModal';
import AgentSwarmStatus from '../components/AgentSwarmStatus';
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
  const navigate = useNavigate();
  const [snapshots, setSnapshots] = useState([]);
  const [opportunities, setOpportunities] = useState([]);
  const [actionLoading, setActionLoading] = useState(false);
  const [qrModalOpen, setQrModalOpen] = useState(false);

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
  const isLiveMode = status?.mode === 'live';
  const holdings = status?.portfolio?.holdings || [];
  const cashBalance = status?.portfolio?.cash_balance_inr || 0;

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

        {/* Start/Stop buttons and Mobile QR */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setQrModalOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-neon-cyan/10 hover:bg-neon-cyan/20 border border-neon-cyan/30 text-neon-cyan text-sm font-heading font-medium transition-all shadow-[0_0_15px_rgba(0,240,255,0.1)]"
            title="Scan QR Code to open dashboard on mobile"
          >
            <QrCode className="w-4 h-4" />
            <span>Mobile QR</span>
            {status?.tunnel?.tunnel_url && (
              <span className="w-2 h-2 rounded-full bg-neon-green animate-pulse" />
            )}
          </button>

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

      {/* Autonomous Agent Swarm Real-time Activity Card */}
      <AgentSwarmStatus onNavigateToAgents={() => navigate('/agents')} />

      {/* CoinDCX Live Wallet Holdings Card */}
      {isLiveMode && holdings.length > 0 && (
        <div className="glass-card p-5 border border-neon-cyan/25 animate-fade-in shadow-[0_0_30px_rgba(0,240,255,0.06)]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-neon-cyan/15 border border-neon-cyan/30 flex items-center justify-center glow-cyan text-neon-cyan">
                <Coins className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-heading font-bold text-white tracking-wide">
                    CoinDCX Live Wallet Holdings
                  </h2>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-neon-green/15 text-neon-green border border-neon-green/30 font-bold flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-ping" />
                    LIVE SPOT ASSETS
                  </span>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  Real-time balances fetched directly from your authenticated CoinDCX exchange wallet
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 text-xs font-mono">
              <div className="text-right">
                <span className="text-gray-400 text-[10px] uppercase block">Total Live Equity</span>
                <span className="text-white font-bold text-sm text-neon-cyan">{formatINR(portfolioValue)}</span>
              </div>
              <div className="text-right pl-3 border-l border-white/10">
                <span className="text-gray-400 text-[10px] uppercase block">Cash (INR)</span>
                <span className="text-gray-200 font-semibold">{formatINR(cashBalance)}</span>
              </div>
            </div>
          </div>

          {/* Holdings Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-sans">
              <thead>
                <tr className="border-b border-white/5 text-[10px] font-mono uppercase text-gray-400">
                  <th className="py-2.5 px-3">Asset</th>
                  <th className="py-2.5 px-3 text-right">Available Qty</th>
                  <th className="py-2.5 px-3 text-right">In Orders</th>
                  <th className="py-2.5 px-3 text-right">Market Price (INR)</th>
                  <th className="py-2.5 px-3 text-right">Estimated Value</th>
                  <th className="py-2.5 px-3 text-right">Portfolio Share</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-mono">
                {holdings.map((h, i) => {
                  const pct = portfolioValue > 0 ? ((h.value_inr / portfolioValue) * 100).toFixed(1) : 0;
                  const isCash = h.currency === 'INR';
                  return (
                    <tr key={i} className="hover:bg-white/[0.03] transition-colors">
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-7 h-7 rounded-md flex items-center justify-center font-bold text-[11px] ${
                            isCash
                              ? 'bg-neon-green/20 text-neon-green border border-neon-green/30'
                              : 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30'
                          }`}>
                            {h.currency.slice(0, 3)}
                          </span>
                          <div>
                            <span className="text-white font-bold block">{h.currency}</span>
                            <span className="text-[10px] text-gray-500">{isCash ? 'Fiat Cash' : 'Spot Crypto'}</span>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-3 text-right text-gray-200 font-medium">
                        {h.available.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                      </td>
                      <td className="py-3 px-3 text-right text-gray-400">
                        {h.locked > 0 ? h.locked.toLocaleString(undefined, { maximumFractionDigits: 6 }) : '—'}
                      </td>
                      <td className="py-3 px-3 text-right text-gray-300">
                        {isCash ? '₹1.00' : formatINR(h.price_inr)}
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-white">
                        {formatINR(h.value_inr)}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className="h-full bg-neon-cyan rounded-full"
                              style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
                            />
                          </div>
                          <span className="text-[11px] text-gray-400 min-w-[36px]">{pct}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

      {/* Mobile QR Code Modal */}
      <MobileQRCodeModal
        isOpen={qrModalOpen}
        onClose={() => setQrModalOpen(false)}
        tunnelData={status?.tunnel}
      />
    </div>
  );
}
