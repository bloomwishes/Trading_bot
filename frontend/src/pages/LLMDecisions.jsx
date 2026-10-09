import { useState, useEffect } from 'react';
import {
  Brain,
  Filter,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Cpu,
  Server,
  Wifi,
  WifiOff,
  RefreshCw,
  Zap,
  ShieldCheck,
  TrendingUp,
  Activity,
  Layers,
} from 'lucide-react';
import {
  getLLMDecisions,
  getLLMStatus,
  getNeuralNetworkTelemetry,
  trainNeuralNetwork,
} from '../utils/api';
import { formatDate } from '../utils/formatters';

export default function LLMDecisions() {
  const [activeTab, setActiveTab] = useState('nn'); // 'nn' or 'llm'
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);
  const [agentStatus, setAgentStatus] = useState(null);
  const [nnTelemetry, setNnTelemetry] = useState(null);
  const [persistedSignals, setPersistedSignals] = useState([]);
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calibrateMessage, setCalibrateMessage] = useState('');

  const [filters, setFilters] = useState({
    pair: '',
    action: '',
    acted_on: '',
  });

  const fetchStatus = async () => {
    try {
      const res = await getLLMStatus();
      setAgentStatus(res.data || null);
    } catch (err) {
      console.error('Failed to fetch LLM status:', err);
    }
  };

  const fetchNeuralTelemetry = async () => {
    try {
      const res = await getNeuralNetworkTelemetry(50);
      if (res.data) {
        setNnTelemetry(res.data.shadow_telemetry || null);
        setPersistedSignals(res.data.persisted_signals || []);
      }
    } catch (err) {
      console.error('Failed to fetch neural network telemetry:', err);
    }
  };

  const fetchDecisions = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.pair) params.pair = filters.pair;
      if (filters.acted_on !== '') params.acted_on = filters.acted_on === 'true';
      const res = await getLLMDecisions(params);
      setDecisions(res.data || []);
    } catch (err) {
      console.error('Failed to fetch LLM decisions:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDecisions();
    fetchStatus();
    fetchNeuralTelemetry();

    // Auto-refresh every 5 seconds
    const interval = setInterval(() => {
      fetchStatus();
      fetchNeuralTelemetry();
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const handleCalibrate = async (pair = 'BTC/INR') => {
    setIsCalibrating(true);
    setCalibrateMessage('');
    try {
      const res = await trainNeuralNetwork(pair);
      setCalibrateMessage(`Calibrated successfully: Loss ${res.data?.metrics?.loss ?? 'OK'}`);
      await fetchNeuralTelemetry();
    } catch (err) {
      console.error('Calibration failed:', err);
      setCalibrateMessage(err?.response?.data?.detail || 'Calibration failed');
    } finally {
      setIsCalibrating(false);
      setTimeout(() => setCalibrateMessage(''), 6000);
    }
  };

  const getActionBadge = (action) => {
    const styles = {
      BUY: 'bg-neon-green/15 text-neon-green border-neon-green/30',
      SELL: 'bg-neon-red/15 text-neon-red border-neon-red/30',
      HOLD: 'bg-neon-yellow/15 text-neon-yellow border-neon-yellow/30',
    };
    return styles[action] || 'bg-gray-800 text-gray-400 border-gray-700';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.70) return { bar: 'bg-neon-green', text: 'text-neon-green' };
    if (confidence >= 0.45) return { bar: 'bg-neon-yellow', text: 'text-neon-yellow' };
    return { bar: 'bg-neon-red', text: 'text-neon-red' };
  };

  const pairs = [...new Set(decisions.map((d) => d.pair))];
  const recentPredictions = nnTelemetry?.recent_predictions || [];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white">
            AI <span className="text-neon-cyan">Intelligence Agent</span>
          </h1>
          <p className="text-gray-400 mt-1">
            Real-time status of the Deep Neural Network & Ollama Language Model
          </p>
        </div>

        {/* Tab Toggle */}
        <div className="flex items-center gap-2 bg-cyber-surface p-1 rounded-xl border border-gray-800">
          <button
            onClick={() => setActiveTab('nn')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'nn'
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40 shadow-[0_0_15px_rgba(0,240,255,0.2)]'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Zap size={14} />
            Deep Neural Network (Active Signals)
          </button>
          <button
            onClick={() => setActiveTab('llm')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'llm'
                ? 'bg-neon-magenta/20 text-neon-magenta border border-neon-magenta/40 shadow-[0_0_15px_rgba(255,0,128,0.2)]'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Brain size={14} />
            Ollama LLM Decisions
          </button>
        </div>
      </div>

      {/* AI Engine Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Neural Network Architecture & Status */}
        <div className="glass-card p-5 flex flex-col justify-between border-l-4 border-l-neon-cyan">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
              <Zap size={14} className="text-neon-cyan" />
              Deep Neural Network
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neon-green/10 border border-neon-green/30 text-neon-green">
              <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />
              Active Signals
            </span>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-neon-cyan/10 border border-neon-cyan/30 flex items-center justify-center glow-cyan">
              <Cpu size={20} className="text-neon-cyan" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white font-mono">16 → 64 → 32 → DualHead</p>
              <p className="text-[10px] text-gray-500">LayerNorm + LeakyReLU + Adam</p>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-cyber-surface/60 flex items-center justify-between text-xs">
            <span className="text-gray-400">Total Steps: <strong className="text-white font-mono">{nnTelemetry?.train_steps ?? 0}</strong></span>
            <span className="text-gray-400">Loss: <strong className="text-neon-cyan font-mono">{nnTelemetry?.last_loss ?? '0.000'}</strong></span>
          </div>
        </div>

        {/* Card 2: Active Trade Execution Mode */}
        <div className="glass-card p-5 flex flex-col justify-between border-l-4 border-l-neon-green">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-neon-green" />
              Execution Mode
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neon-green/15 border border-neon-green/30 text-neon-green">
              ⚡ Active Signals Enabled
            </span>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-neon-green/10 border border-neon-green/30 flex items-center justify-center">
              <Layers size={20} className="text-neon-green" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Active Signal Execution & ATR Guard</p>
              <p className="text-[10px] text-gray-400">Emits BUY/SELL signals; executes live paper trades</p>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-cyber-surface/60 flex items-center justify-between text-xs">
            <span className="text-gray-400">Inferences: <strong className="text-white font-mono">{nnTelemetry?.total_predictions ?? 0}</strong></span>
            <span className="text-gray-400">Signals Saved: <strong className="text-neon-green font-mono">{persistedSignals.length}</strong></span>
          </div>
        </div>

        {/* Card 3: Ollama Connection */}
        <div className="glass-card p-5 flex flex-col justify-between border-l-4 border-l-neon-magenta">
          <div className="flex items-center justify-between">
            <span className="text-gray-400 text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5">
              <Brain size={14} className="text-neon-magenta" />
              Ollama LLM Agent
            </span>
            {agentStatus?.connected ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neon-green/10 border border-neon-green/30 text-neon-green">
                <Wifi size={12} /> Connected
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neon-red/10 border border-neon-red/30 text-neon-red">
                <WifiOff size={12} /> Standby / Offline
              </span>
            )}
          </div>

          <div className="mt-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-neon-magenta/10 border border-neon-magenta/30 flex items-center justify-center">
              <Server size={20} className="text-neon-magenta" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white font-mono">{agentStatus?.configured_model || 'llama3'}</p>
              <p className="text-[10px] text-gray-500 font-mono">{agentStatus?.host || 'http://localhost:11434'}</p>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-cyber-surface/60 flex items-center justify-between text-xs">
            <span className="text-gray-400">Status: <strong className="text-white">{agentStatus?.status || 'Idle'}</strong></span>
            <span className="text-gray-400">Decisions: <strong className="text-neon-magenta font-mono">{decisions.length}</strong></span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: DEEP NEURAL NETWORK (SHADOW MODE) VIEW                             */}
      {/* ========================================================================= */}
      {activeTab === 'nn' && (
        <div className="space-y-6">
          {/* Action Bar / Calibrate Control */}
          <div className="glass-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-cyber-surface border border-gray-700 flex items-center justify-center">
                <Activity size={18} className="text-neon-cyan animate-pulse" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Live Neural Signal Feed & Online Learning</h3>
                <p className="text-xs text-gray-400">
                  Calibrated on: {nnTelemetry?.trained_pairs?.join(', ') || 'BTC/INR'} (15m Candles)
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {calibrateMessage && (
                <span className="text-xs text-neon-cyan font-mono animate-fade-in">
                  {calibrateMessage}
                </span>
              )}
              <button
                onClick={() => handleCalibrate('BTC/INR')}
                disabled={isCalibrating}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-neon-cyan/20 border border-neon-cyan/40 text-neon-cyan hover:bg-neon-cyan/30 transition-all shadow-[0_0_12px_rgba(0,240,255,0.15)] disabled:opacity-50"
              >
                <RefreshCw size={14} className={isCalibrating ? 'animate-spin' : ''} />
                {isCalibrating ? 'Calibrating Weights...' : 'Calibrate on BTC/INR'}
              </button>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 uppercase mb-1">Inferences</div>
              <div className="text-2xl font-bold font-mono text-neon-cyan">
                {nnTelemetry?.total_predictions ?? 0}
              </div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 uppercase mb-1">Input Features</div>
              <div className="text-2xl font-bold font-mono text-neon-green">16 Indicators</div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 uppercase mb-1">Training Epochs</div>
              <div className="text-2xl font-bold font-mono text-neon-yellow">
                {nnTelemetry?.train_steps ?? 0}
              </div>
            </div>
            <div className="glass-card p-4">
              <div className="text-xs text-gray-500 uppercase mb-1">Trading Mode</div>
              <div className="text-2xl font-bold font-mono text-neon-green">⚡ Active Signals</div>
            </div>
          </div>

          {/* Recent Neural Predictions Table */}
          <div className="glass-card overflow-hidden">
            <div className="p-4 border-b border-cyber-surface flex items-center justify-between">
              <h3 className="font-heading text-sm font-bold text-white flex items-center gap-2">
                <TrendingUp size={16} className="text-neon-cyan" />
                Latest Neural Network Trading Signals & Decisions
              </h3>
              <span className="text-xs text-gray-500 font-mono">
                Auto-updating every 5s • Top {recentPredictions.length} inferences
              </span>
            </div>

            {recentPredictions.length === 0 ? (
              <div className="p-16 text-center">
                <Zap size={48} className="mx-auto mb-4 text-gray-700" />
                <h3 className="text-lg font-heading text-gray-500 mb-2">Awaiting Market Cycles</h3>
                <p className="text-gray-600 text-sm mb-4">
                  The neural network runs inferences automatically as each 15-minute candle updates.
                </p>
                <button
                  onClick={() => handleCalibrate('BTC/INR')}
                  disabled={isCalibrating}
                  className="px-4 py-2 rounded-lg text-xs font-semibold bg-neon-cyan/20 border border-neon-cyan/40 text-neon-cyan hover:bg-neon-cyan/30"
                >
                  Run Calibration Now
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-neon-cyan/10">
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Pair & Price</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Prediction</th>
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase w-48">Confidence</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Expected Return</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Probability Vector</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Mode</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cyber-surface/30">
                    {recentPredictions.map((pred, idx) => {
                      const confColor = getConfidenceColor(pred.confidence || 0);
                      const probs = pred.probabilities || {};

                      return (
                        <tr key={idx} className="hover:bg-cyber-surface/20 transition-colors">
                          <td className="p-4 text-sm text-gray-400 font-mono">
                            {formatDate(pred.timestamp)}
                          </td>
                          <td className="p-4">
                            <span className="font-semibold text-white block">{pred.pair}</span>
                            <span className="text-xs text-gray-500 font-mono">
                              ₹{Number(pred.price || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </span>
                          </td>
                          <td className="p-4 text-center">
                            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getActionBadge(pred.action)}`}>
                              {pred.action}
                            </span>
                          </td>
                          <td className="p-4">
                            <div className="flex items-center gap-3">
                              <div className="flex-1 h-2 bg-cyber-surface rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-500 ${confColor.bar}`}
                                  style={{ width: `${Math.min(100, (pred.confidence || 0) * 100)}%` }}
                                />
                              </div>
                              <span className={`text-xs font-bold font-mono ${confColor.text} min-w-[3rem] text-right`}>
                                {((pred.confidence || 0) * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="p-4 text-center">
                            <span
                              className={`text-sm font-mono font-bold ${
                                (pred.expected_return_pct || 0) >= 0 ? 'text-neon-green' : 'text-neon-red'
                              }`}
                            >
                              {(pred.expected_return_pct || 0) >= 0 ? '+' : ''}
                              {Number(pred.expected_return_pct || 0).toFixed(2)}%
                            </span>
                          </td>
                          <td className="p-4 text-center">
                            <div className="inline-flex items-center gap-1.5 text-[11px] font-mono bg-cyber-surface/60 px-2.5 py-1 rounded-lg border border-gray-800">
                              <span className="text-gray-400">H: <strong className="text-neon-yellow">{(probs.HOLD * 100 || 0).toFixed(0)}%</strong></span>
                              <span className="text-gray-500">|</span>
                              <span className="text-gray-400">B: <strong className="text-neon-green">{(probs.BUY * 100 || 0).toFixed(0)}%</strong></span>
                              <span className="text-gray-500">|</span>
                              <span className="text-gray-400">S: <strong className="text-neon-red">{(probs.SELL * 100 || 0).toFixed(0)}%</strong></span>
                            </div>
                          </td>
                          <td className="p-4 text-center">
                            <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-neon-green/15 text-neon-green border border-neon-green/30 font-semibold shadow-[0_0_8px_rgba(0,255,102,0.15)]">
                              ⚡ ACTIVE SIGNAL
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: OLLAMA LLM DECISIONS VIEW                                          */}
      {/* ========================================================================= */}
      {activeTab === 'llm' && (
        <div className="space-y-6">
          {/* Filters */}
          <div className="glass-card p-4">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Filter size={16} />
                <span>Filter:</span>
              </div>
              <select
                value={filters.pair}
                onChange={(e) => setFilters((p) => ({ ...p, pair: e.target.value }))}
                className="bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-neon-cyan/50 focus:outline-none transition-colors"
              >
                <option value="">All Pairs</option>
                {pairs.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>

              <div className="flex gap-2">
                {['', 'BUY', 'SELL', 'HOLD'].map((action) => (
                  <button
                    key={action || 'all'}
                    onClick={() => setFilters((p) => ({ ...p, action }))}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                      filters.action === action
                        ? 'bg-neon-cyan/20 border-neon-cyan/40 text-neon-cyan'
                        : 'bg-cyber-surface border-gray-700 text-gray-500 hover:border-gray-500'
                    }`}
                  >
                    {action || 'All'}
                  </button>
                ))}
              </div>

              <select
                value={filters.acted_on}
                onChange={(e) => setFilters((p) => ({ ...p, acted_on: e.target.value }))}
                className="bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-neon-cyan/50 focus:outline-none transition-colors"
              >
                <option value="">Acted: All</option>
                <option value="true">Executed</option>
                <option value="false">Not Executed</option>
              </select>

              <button
                onClick={fetchDecisions}
                className="px-4 py-1.5 rounded-lg bg-neon-cyan/15 border border-neon-cyan/30 text-neon-cyan text-sm hover:bg-neon-cyan/25 transition-all"
              >
                Apply
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Decisions', value: decisions.length, color: 'text-neon-cyan' },
              { label: 'Executed', value: decisions.filter((d) => d.acted_on).length, color: 'text-neon-green' },
              {
                label: 'Avg Confidence',
                value: decisions.length
                  ? `${((decisions.reduce((s, d) => s + (d.confidence || 0), 0) / decisions.length) * 100).toFixed(0)}%`
                  : '—',
                color: 'text-neon-yellow',
              },
              {
                label: 'High Confidence',
                value: decisions.filter((d) => (d.confidence || 0) >= 0.75).length,
                color: 'text-neon-magenta',
              },
            ].map((stat, i) => (
              <div key={i} className="glass-card p-4">
                <div className="text-xs text-gray-500 uppercase mb-1">{stat.label}</div>
                <div className={`text-2xl font-bold font-mono ${stat.color}`}>{stat.value}</div>
              </div>
            ))}
          </div>

          {/* Decisions Table */}
          <div className="glass-card overflow-hidden">
            {loading ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-16 bg-cyber-surface/50 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : decisions.length === 0 ? (
              <div className="p-16 text-center">
                <Brain size={48} className="mx-auto mb-4 text-gray-700" />
                <h3 className="text-lg font-heading text-gray-500 mb-2">No LLM Decisions Yet</h3>
                <p className="text-gray-600 text-sm">
                  The Sentiment LLM strategy will log decisions here when Ollama is running and active.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-neon-cyan/10">
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Pair</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Action</th>
                      <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase w-48">Confidence</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Executed</th>
                      <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cyber-surface/30">
                    {decisions
                      .filter((d) => !filters.action || d.action === filters.action)
                      .map((decision) => {
                        const confColor = getConfidenceColor(decision.confidence || 0);
                        const isExpanded = expandedRow === decision.id;

                        return (
                          <>
                            <tr
                              key={decision.id}
                              className="hover:bg-cyber-surface/20 transition-colors duration-200 cursor-pointer"
                              onClick={() => setExpandedRow(isExpanded ? null : decision.id)}
                            >
                              <td className="p-4 text-sm text-gray-400">{formatDate(decision.created_at)}</td>
                              <td className="p-4">
                                <span className="font-semibold text-white">{decision.pair}</span>
                              </td>
                              <td className="p-4 text-center">
                                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getActionBadge(decision.action)}`}>
                                  {decision.action}
                                </span>
                              </td>
                              <td className="p-4">
                                <div className="flex items-center gap-3">
                                  <div className="flex-1 h-2.5 bg-cyber-surface rounded-full overflow-hidden">
                                    <div
                                      className={`h-full rounded-full transition-all duration-500 ${confColor.bar}`}
                                      style={{ width: `${(decision.confidence || 0) * 100}%` }}
                                    />
                                  </div>
                                  <span className={`text-sm font-bold font-mono ${confColor.text} min-w-[3rem] text-right`}>
                                    {((decision.confidence || 0) * 100).toFixed(0)}%
                                  </span>
                                </div>
                              </td>
                              <td className="p-4 text-center">
                                {decision.acted_on ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-neon-green/15 text-neon-green border border-neon-green/30">
                                    <CheckCircle size={12} /> Yes
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-gray-800 text-gray-500 border border-gray-700">
                                    <XCircle size={12} /> No
                                  </span>
                                )}
                              </td>
                              <td className="p-4 text-center">
                                {isExpanded ? (
                                  <ChevronUp size={18} className="mx-auto text-neon-cyan" />
                                ) : (
                                  <ChevronDown size={18} className="mx-auto text-gray-500" />
                                )}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr key={`${decision.id}-detail`}>
                                <td colSpan="6" className="p-0">
                                  <div className="px-6 py-4 bg-cyber-surface/30 border-l-2 border-neon-cyan/30 animate-slide-in">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <div>
                                        <h4 className="text-xs text-gray-500 uppercase mb-2 flex items-center gap-1">
                                          <Brain size={12} /> AI Reasoning
                                        </h4>
                                        <p className="text-sm text-gray-300 leading-relaxed bg-cyber-bg/50 rounded-lg p-3">
                                          {decision.reason || 'No reasoning provided'}
                                        </p>
                                      </div>
                                      <div>
                                        <h4 className="text-xs text-gray-500 uppercase mb-2">Full Response</h4>
                                        <pre className="text-xs text-gray-500 bg-cyber-bg/50 rounded-lg p-3 overflow-x-auto max-h-32 font-mono">
                                          {decision.response || '—'}
                                        </pre>
                                      </div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
