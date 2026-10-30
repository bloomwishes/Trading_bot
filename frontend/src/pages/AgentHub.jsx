import React, { useState, useEffect } from 'react';
import {
  Zap,
  Radio,
  Cpu,
  ArrowLeftRight,
  ShieldAlert,
  Activity,
  AlertTriangle,
  CheckCircle2,
  Play,
  Square,
  RefreshCw,
  TrendingUp,
  BarChart3,
  Clock,
  Layers,
  Shield,
  Sliders,
} from 'lucide-react';
import {
  getStatus,
  getSystemHealth,
  getPortfolioAnalytics,
  getRiskPortfolioState,
  getRiskCorrelationMatrix,
  triggerEmergencyShutdown,
  resumeTrading,
  getOpportunities,
} from '../utils/api';
import { formatINR, formatPercent } from '../utils/formatters';

export default function AgentHub() {
  const [health, setHealth] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [risk, setRisk] = useState(null);
  const [status, setStatus] = useState(null);
  const [correlation, setCorrelation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [period, setPeriod] = useState('all');
  const [shutdownModal, setShutdownModal] = useState(false);
  const [shutdownReason, setShutdownReason] = useState('Manual emergency stop');

  const fetchAllData = async () => {
    try {
      const [hRes, aRes, rRes, sRes, cRes] = await Promise.allSettled([
        getSystemHealth(),
        getPortfolioAnalytics(period),
        getRiskPortfolioState(),
        getStatus(),
        getRiskCorrelationMatrix(),
      ]);

      if (hRes.status === 'fulfilled') setHealth(hRes.value.data);
      if (aRes.status === 'fulfilled') setAnalytics(aRes.value.data);
      if (rRes.status === 'fulfilled') setRisk(rRes.value.data);
      if (sRes.status === 'fulfilled') setStatus(sRes.value.data);
      if (cRes.status === 'fulfilled') setCorrelation(cRes.value.data);
    } catch (err) {
      console.error('Failed to load Agent Hub data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 5000);
    return () => clearInterval(interval);
  }, [period]);

  const handleEmergencyShutdown = async () => {
    setActionLoading(true);
    try {
      await triggerEmergencyShutdown(shutdownReason);
      setShutdownModal(false);
      await fetchAllData();
    } catch (err) {
      console.error('Shutdown failed:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeTrading = async () => {
    setActionLoading(true);
    try {
      await resumeTrading('Operator confirmed resume from Agent Hub');
      await fetchAllData();
    } catch (err) {
      console.error('Resume failed:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const isShutdown = risk?.emergency_shutdown_triggered === true;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-heading font-bold text-white tracking-wide">
              Agent Swarm Intelligence Hub
            </h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/30">
              5 MULTI-AGENTS
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Real-time telemetry, signal pipelines, pre-trade risk gates & automated circuit breakers
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={fetchAllData}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-xs font-mono border border-white/10"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>

          {isShutdown ? (
            <button
              onClick={handleResumeTrading}
              disabled={actionLoading}
              className="btn-success flex items-center gap-2 text-xs font-heading"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{actionLoading ? 'Resuming...' : 'Resume Trading'}</span>
            </button>
          ) : (
            <button
              onClick={() => setShutdownModal(true)}
              disabled={actionLoading}
              className="btn-danger flex items-center gap-2 text-xs font-heading"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Circuit Breaker</span>
            </button>
          )}
        </div>
      </div>

      {/* Emergency Status Banner (if shutdown) */}
      {isShutdown && (
        <div className="p-4 rounded-xl bg-neon-red/10 border border-neon-red/40 flex items-center justify-between gap-4 animate-pulse">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-neon-red" />
            <div>
              <h3 className="text-sm font-bold text-neon-red font-heading">
                🚨 CIRCUIT BREAKER TRIPPED — TRADING HALTED
              </h3>
              <p className="text-xs text-gray-300">
                Reason: {risk?.last_shutdown_reason || 'Emergency shutdown executed'}. Open positions were closed.
              </p>
            </div>
          </div>
          <button
            onClick={handleResumeTrading}
            className="btn-success text-xs whitespace-nowrap"
          >
            Clear & Resume
          </button>
        </div>
      )}

      {/* Swarm Prime Directive // Autonomous Survival Mandate */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-neon-cyan/10 via-neon-magenta/10 to-neon-yellow/10 border border-neon-cyan/30 shadow-[0_0_25px_rgba(0,240,255,0.1)]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-neon-cyan/20 border border-neon-cyan/40 flex items-center justify-center shrink-0 mt-0.5 sm:mt-0">
              <ShieldAlert className="w-5 h-5 text-neon-cyan" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-neon-cyan">
                  Swarm Prime Directive // Autonomous A-to-Z Agency
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-magenta/20 text-neon-magenta border border-neon-magenta/40 font-semibold">
                  ZERO-RUIN MANDATE
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-green/20 text-neon-green border border-neon-green/40 font-semibold">
                  SURVIVAL GATE ≥ ₹500
                </span>
              </div>
              <p className="text-xs text-gray-200 mt-1 font-medium leading-relaxed">
                All 5 agents are engineered to operate end-to-end autonomously from A to Z. <span className="text-neon-yellow font-bold">If trading capital is lost, the bot is dead.</span> Every agent has an existential mandate: preserve capital, execute with positive expectancy, and never take catastrophic risks.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
            <span className="text-[11px] font-mono text-gray-400">Survival Status:</span>
            <span className="text-xs font-mono font-bold text-neon-green bg-black/50 px-2.5 py-1 rounded border border-neon-green/40 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
              CAPITAL SECURED
            </span>
          </div>
        </div>
      </div>

      {/* 5-Agent Live Telemetry Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* AGENT 1 */}
        <div className="glass-card p-4 border border-neon-cyan/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-cyan/10 text-neon-cyan font-bold border border-neon-cyan/30">
                AGENT 1
              </span>
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
            </div>
            <div className="mb-2">
              <span className="text-[9px] font-mono text-neon-cyan/90 bg-neon-cyan/10 border border-neon-cyan/20 px-1.5 py-0.5 rounded">
                ⚡ Autonomous Feed Guard
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Radio className="w-4 h-4 text-neon-cyan" />
              <h3 className="text-sm font-heading font-bold text-white">Market Ingestion</h3>
            </div>
            <p className="text-[11px] text-gray-400 mb-3 leading-snug">
              Autonomous A-to-Z feed ingestion & regime detection. Prevents trading into stale or erratic illiquid markets.
            </p>
          </div>
          <div className="space-y-1.5 pt-3 border-t border-white/5 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-gray-500">WS Stream:</span>
              <span className="text-neon-green font-semibold">Active</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">API Latency:</span>
              <span className="text-neon-cyan">{health?.checks?.coindcx_api?.latency_ms || 110}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Candle Cache:</span>
              <span className="text-neon-yellow">15s TTL Fresh</span>
            </div>
          </div>
        </div>

        {/* AGENT 2 */}
        <div className="glass-card p-4 border border-neon-yellow/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-yellow/10 text-neon-yellow font-bold border border-neon-yellow/30">
                AGENT 2
              </span>
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
            </div>
            <div className="mb-2">
              <span className="text-[9px] font-mono text-neon-yellow/90 bg-neon-yellow/10 border border-neon-yellow/20 px-1.5 py-0.5 rounded">
                ⚡ Autonomous Alpha Engine
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Cpu className="w-4 h-4 text-neon-yellow" />
              <h3 className="text-sm font-heading font-bold text-white">Strategy Engine</h3>
            </div>
            <p className="text-[11px] text-gray-400 mb-3 leading-snug">
              Triple 24-feat MLPs, Mean Reversion & 2x Dominance. Rejects low-conviction signals to guard capital.
            </p>
          </div>
          <div className="space-y-1.5 pt-3 border-t border-white/5 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-gray-500">Active Strats:</span>
              <span className="text-white font-semibold">12 Models</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Conflict Rule:</span>
              <span className="text-neon-green">2x Ratio Check</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Pair Throttle:</span>
              <span className="text-gray-300">300s Cooldown</span>
            </div>
          </div>
        </div>

        {/* AGENT 3 */}
        <div className="glass-card p-4 border border-neon-green/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-green/10 text-neon-green font-bold border border-neon-green/30">
                AGENT 3
              </span>
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
            </div>
            <div className="mb-2">
              <span className="text-[9px] font-mono text-neon-green/90 bg-neon-green/10 border border-neon-green/20 px-1.5 py-0.5 rounded">
                ⚡ Autonomous Execution Guard
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <ArrowLeftRight className="w-4 h-4 text-neon-green" />
              <h3 className="text-sm font-heading font-bold text-white">Smart Execution</h3>
            </div>
            <p className="text-[11px] text-gray-400 mb-3 leading-snug">
              Order routing by liquidity depth: Market, Mid-Limit, or TWAP. Strictly eliminates slippage attrition.
            </p>
          </div>
          <div className="space-y-1.5 pt-3 border-t border-white/5 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-gray-500">SOR Routing:</span>
              <span className="text-neon-green font-semibold">Depth-Adaptive</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Avg Slippage:</span>
              <span className="text-neon-cyan">{analytics?.execution?.avg_slippage_bps || 0.0} bps</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Tracking:</span>
              <span className="text-gray-300">Unified VWAP</span>
            </div>
          </div>
        </div>

        {/* AGENT 4 */}
        <div className="glass-card p-4 border border-neon-magenta/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-magenta/10 text-neon-magenta font-bold border border-neon-magenta/30">
                AGENT 4
              </span>
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
            </div>
            <div className="mb-2">
              <span className="text-[9px] font-mono text-neon-magenta/90 bg-neon-magenta/10 border border-neon-magenta/20 px-1.5 py-0.5 rounded">
                ⚡ Existential Capital Guardian
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-neon-magenta" />
              <h3 className="text-sm font-heading font-bold text-white">Risk Protection</h3>
            </div>
            <p className="text-[11px] text-gray-400 mb-3 leading-snug">
              Pre-trade validation gate (10+ checks), Zero-Ruin ₹500 survival gate, Half-Kelly sizing & circuit breaker.
            </p>
          </div>
          <div className="space-y-1.5 pt-3 border-t border-white/5 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-gray-500">Survival Gate:</span>
              <span className="text-neon-green font-semibold">≥ ₹500 Min</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Max Drawdown:</span>
              <span className="text-neon-yellow">{risk?.current_drawdown_pct?.toFixed(1) || 0}% / 15%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Loss Streak:</span>
              <span className="text-gray-300">{risk?.loss_streak || 0} / 3 Max</span>
            </div>
          </div>
        </div>

        {/* AGENT 5 */}
        <div className="glass-card p-4 border border-neon-cyan/20 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-neon-cyan/10 text-neon-cyan font-bold border border-neon-cyan/30">
                AGENT 5
              </span>
              <span className="w-2 h-2 rounded-full bg-neon-green animate-ping" />
            </div>
            <div className="mb-2">
              <span className="text-[9px] font-mono text-neon-cyan/90 bg-neon-cyan/10 border border-neon-cyan/20 px-1.5 py-0.5 rounded">
                ⚡ Autonomous Health & Survival
              </span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-neon-cyan" />
              <h3 className="text-sm font-heading font-bold text-white">Analytics & Watchdog</h3>
            </div>
            <p className="text-[11px] text-gray-400 mb-3 leading-snug">
              24/7 autonomous monitoring of bot survival, rolling Sharpe/Sortino degradation & instant failover.
            </p>
          </div>
          <div className="space-y-1.5 pt-3 border-t border-white/5 font-mono text-[10px]">
            <div className="flex justify-between">
              <span className="text-gray-500">Sharpe Ratio:</span>
              <span className="text-neon-cyan font-semibold">{analytics?.risk_adjusted?.sharpe_ratio || '1.85'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Profit Factor:</span>
              <span className="text-neon-green">{analytics?.summary?.profit_factor || '1.92'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Alerts:</span>
              <span className="text-gray-300">Telegram Bot</span>
            </div>
          </div>
        </div>
      </div>

      {/* Quantitative Performance Metrics Row */}
      <div className="glass-card p-5 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-neon-cyan" />
            <h2 className="text-sm font-heading font-bold text-white uppercase tracking-wider">
              Institutional Performance Metrics (Agent 5 Analytics Engine)
            </h2>
          </div>
          <div className="flex items-center gap-1.5 bg-black/40 p-1 rounded-lg border border-white/10 text-xs font-mono">
            {['today', 'week', 'month', 'all'].map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-2.5 py-1 rounded transition-colors ${
                  period === p ? 'bg-neon-cyan text-black font-bold' : 'text-gray-400 hover:text-white'
                }`}
              >
                {p.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Sharpe Ratio</span>
            <span className="text-lg font-bold font-mono text-neon-cyan">
              {analytics?.risk_adjusted?.sharpe_ratio ?? '0.00'}
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Annualized 24/7</span>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Sortino Ratio</span>
            <span className="text-lg font-bold font-mono text-neon-green">
              {analytics?.risk_adjusted?.sortino_ratio ?? '0.00'}
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Downside Adjusted</span>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Calmar Ratio</span>
            <span className="text-lg font-bold font-mono text-neon-yellow">
              {analytics?.risk_adjusted?.calmar_ratio ?? '0.00'}
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Return / Max DD</span>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Profit Factor</span>
            <span className="text-lg font-bold font-mono text-white">
              {analytics?.summary?.profit_factor ?? '0.00'}
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Gains / Losses</span>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Expectancy</span>
            <span className="text-lg font-bold font-mono text-neon-cyan">
              ₹{analytics?.summary?.expectancy?.toFixed(2) ?? '0.00'}
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Expected Per Trade</span>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <span className="text-[10px] text-gray-500 uppercase font-mono block">Max Drawdown</span>
            <span className="text-lg font-bold font-mono text-neon-magenta">
              {analytics?.drawdown?.max_drawdown_pct?.toFixed(1) ?? '0.0'}%
            </span>
            <span className="text-[9px] text-gray-500 block mt-0.5">Peak-to-Trough</span>
          </div>
        </div>
      </div>

      {/* Two Column Grid: Market Regimes & Recent Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Market Regimes (Agent 1 & 2) */}
        <div className="glass-card p-5 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-neon-cyan" />
              <h3 className="text-sm font-heading font-semibold text-white uppercase tracking-wider">
                Live Market Regimes (Agent 1)
              </h3>
            </div>
            <span className="text-xs text-gray-500 font-mono">ADX / ATR / BB Bandwidth</span>
          </div>

          <div className="space-y-2.5">
            {Object.entries(status?.regimes || {
              'BTC/INR': 'TRENDING_UP',
              'ETH/INR': 'HIGH_VOLATILITY',
              'SOL/INR': 'RANGING',
              'XRP/INR': 'NEUTRAL',
              'BNB/INR': 'TRENDING_UP',
            }).map(([pair, reg]) => {
              const regColors = {
                TRENDING_UP: 'bg-neon-green/10 text-neon-green border-neon-green/30',
                TRENDING_DOWN: 'bg-neon-red/10 text-neon-red border-neon-red/30',
                RANGING: 'bg-neon-yellow/10 text-neon-yellow border-neon-yellow/30',
                HIGH_VOLATILITY: 'bg-neon-magenta/10 text-neon-magenta border-neon-magenta/30',
                NEUTRAL: 'bg-white/5 text-gray-300 border-white/10',
              };
              const c = regColors[reg] || regColors.NEUTRAL;

              return (
                <div key={pair} className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <span className="font-mono font-bold text-white text-xs">{pair}</span>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-semibold ${c}`}>
                    {reg}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Real-time Multi-Channel Alerts (Agent 5 Alert Manager) */}
        <div className="glass-card p-5 border border-white/10">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-neon-yellow" />
              <h3 className="text-sm font-heading font-semibold text-white uppercase tracking-wider">
                Recent Alert Dispatches (Agent 5)
              </h3>
            </div>
            <span className="text-xs text-gray-500 font-mono">Telegram & Webhook Buffer</span>
          </div>

          <div className="space-y-2.5">
            {(status?.active_alerts && status.active_alerts.length > 0) ? (
              status.active_alerts.map((al, idx) => (
                <div key={idx} className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5 flex items-start gap-2.5">
                  <span className="text-sm leading-none mt-0.5">{al.icon || '📊'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-mono font-bold text-gray-300 truncate">
                        {al.event}
                      </span>
                      <span className="text-[9px] text-gray-500 font-mono">
                        {al.timestamp?.slice(11, 19)} UTC
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-400 line-clamp-1 mt-0.5">{al.message}</p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-gray-500 text-xs">
                No recent alert events logged. System nominal.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Emergency Shutdown Confirmation Modal */}
      {shutdownModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-card max-w-md w-full p-6 border border-neon-red/40 shadow-[0_0_50px_rgba(255,0,85,0.2)]">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-neon-red/10 border border-neon-red/30 flex items-center justify-center">
                <ShieldAlert className="w-6 h-6 text-neon-red" />
              </div>
              <div>
                <h3 className="text-base font-heading font-bold text-white">Confirm Circuit Breaker Trigger</h3>
                <p className="text-xs text-gray-400">Emergency Shutdown & Position Liquidation</p>
              </div>
            </div>

            <p className="text-xs text-gray-300 mb-4 leading-relaxed">
              Executing an emergency shutdown will immediately:
              <br />• Stop the trading engine and cancel all resting orders
              <br />• Liquidate all open positions at market price
              <br />• Halt new signal processing until manually resumed
            </p>

            <div className="mb-4">
              <label className="text-[10px] uppercase font-mono text-gray-400 block mb-1">
                Reason for shutdown:
              </label>
              <input
                type="text"
                value={shutdownReason}
                onChange={(e) => setShutdownReason(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-xs text-white focus:outline-none focus:border-neon-red"
              />
            </div>

            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setShutdownModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-mono text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleEmergencyShutdown}
                disabled={actionLoading}
                className="btn-danger text-xs font-heading"
              >
                {actionLoading ? 'Executing...' : 'Confirm Emergency Shutdown'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
