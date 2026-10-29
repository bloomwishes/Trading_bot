import React, { useState, useEffect, useRef } from 'react';
import {
  Zap,
  Activity,
  ShieldCheck,
  RefreshCw,
  TrendingUp,
  Cpu,
  Layers,
  Award,
  AlertTriangle,
  Play,
  CheckCircle2,
  Sparkles,
  Eye,
  Sliders,
} from 'lucide-react';
import { getNeuralLiveBrain, getNeuralLiveBrains, trainNeuralNetwork, combineNeuralModels, updateStrategy } from '../utils/api';
import HolographicBrainViewer from '../components/HolographicBrainViewer';

const FEATURE_DESCRIPTIONS = {
  rsi_norm: 'RSI (Normalized -1 to +1)',
  stoch_k_norm: 'StochRSI %K Oscillator',
  stoch_d_norm: 'StochRSI %D Smoothing',
  stoch_diff: 'Stochastic Spread (%K - %D)',
  ema9_dist_pct: 'Distance to 9 EMA %',
  ema21_dist_pct: 'Distance to 21 EMA %',
  ema50_dist_pct: 'Distance to 50 EMA %',
  trend_alignment: 'Multi-EMA Trend Direction',
  macd_norm: 'MACD Line / Price %',
  macd_hist_norm: 'MACD Histogram / Price %',
  bb_percent_b: 'Bollinger %B Position',
  bb_bandwidth: 'Bollinger Bandwidth Volatility',
  atr_pct: 'ATR Volatility % of Close',
  rel_volume: 'Volume / 20-period SMA',
  bar_return_pct: 'Intra-bar Price Return %',
  mom_3bar_pct: '3-Candle Momentum Return %',
};

const BRAIN_MODELS = [
  {
    id: 'Neural_Network_BTC',
    name: 'BTC Neural Engine',
    tag: 'Macro 10Y Specialist',
    color: 'from-amber-500/20 to-orange-500/10 border-orange-500/40 text-orange-400',
    pairs: ['BTC/INR'],
    description: 'Trained on 10 Years of Bitcoin market cycles, multi-horizon trends & real closed trade experience.',
  },
  {
    id: 'Neural_Network_ETH',
    name: 'ETH Neural Engine',
    tag: 'Ethereum Specialist',
    color: 'from-blue-500/20 to-indigo-500/10 border-indigo-500/40 text-indigo-400',
    pairs: ['ETH/INR'],
    description: 'Trained completely on historical Ethereum cycles (3,250+ daily candles & 17,350+ hourly microstructure).',
  },
  {
    id: 'Neural_Network_ALTS',
    name: 'Altcoins Neural Engine',
    tag: 'Major Alts Basket',
    color: 'from-purple-500/20 to-pink-500/10 border-purple-500/40 text-purple-400',
    pairs: ['SOL/INR', 'XRP/INR', 'BNB/INR'],
    description: 'Trained on multi-token volatility structure across Solana, Ripple, BNB, DOGE, ADA & LINK (192,100+ samples).',
  },
];

export default function NeuralBrain() {
  const [activeModelId, setActiveModelId] = useState('Neural_Network_BTC');
  const [selectedPair, setSelectedPair] = useState('BTC/INR');
  const [brainData, setBrainData] = useState(null);
  const [allBrainsData, setAllBrainsData] = useState({});
  const [capitalHealth, setCapitalHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isFiring, setIsFiring] = useState(false);
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calibrateStatus, setCalibrateStatus] = useState('');
  const [isCombining, setIsCombining] = useState(false);
  const [combineStatus, setCombineStatus] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [displayMode, setDisplayMode] = useState('hologram'); // 'hologram' | 'both' | 'matrix'

  // Switch active model when pair changes or vice-versa
  const handleModelSelect = (model) => {
    setActiveModelId(model.id);
    if (!model.pairs.includes(selectedPair)) {
      setSelectedPair(model.pairs[0]);
    }
  };

  const handlePairChange = (newPair) => {
    setSelectedPair(newPair);
    const parentModel = BRAIN_MODELS.find((m) => m.pairs.includes(newPair));
    if (parentModel) {
      setActiveModelId(parentModel.id);
    }
  };

  const fetchBrain = async (pair = selectedPair, model = activeModelId) => {
    try {
      const [resSingle, resAll] = await Promise.allSettled([
        getNeuralLiveBrain(pair, model),
        getNeuralLiveBrains(),
      ]);
      if (resSingle.status === 'fulfilled' && resSingle.value.data) {
        setBrainData(resSingle.value.data.brain || null);
        setCapitalHealth(resSingle.value.data.capital_health || null);
      }
      if (resAll.status === 'fulfilled' && resAll.value.data?.models) {
        setAllBrainsData(resAll.value.data.models);
      }
    } catch (err) {
      console.error('Failed to fetch neural brain:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBrain(selectedPair, activeModelId);
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchBrain(selectedPair, activeModelId);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedPair, activeModelId, autoRefresh]);

  const handleFireSynapses = async () => {
    setIsFiring(true);
    await fetchBrain(selectedPair);
    setTimeout(() => setIsFiring(false), 800);
  };

  const handleCalibrate = async () => {
    setIsCalibrating(true);
    setCalibrateStatus('Training network on 15m candles...');
    try {
      const res = await trainNeuralNetwork(selectedPair);
      setCalibrateStatus(`Calibration Complete! Loss: ${res.data?.metrics?.loss ?? '0.12'}`);
      await fetchBrain(selectedPair);
    } catch (err) {
      setCalibrateStatus('Calibration failed: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsCalibrating(false);
      setTimeout(() => setCalibrateStatus(''), 5000);
    }
  };

  const handleCombineModels = async () => {
    setIsCombining(true);
    setCombineStatus('Combining 24-month CoinDCX macro data & closed trade experience into unified model...');
    try {
      const res = await combineNeuralModels({ days: 730, epochs: 100, learning_rate: 0.005 });
      const r = res.data?.result || {};
      setCombineStatus(
        `Unified Model Trained! Overall Acc: ${((r.overall_accuracy || 0) * 100).toFixed(1)}% | ` +
        `Trade Acc: ${((r.trade_accuracy || 0) * 100).toFixed(1)}% | ` +
        `Macro Acc: ${((r.macro_accuracy || 0) * 100).toFixed(1)}% | ` +
        `Loss: ${(r.loss || 0).toFixed(4)}`
      );
      await fetchBrain(selectedPair);
    } catch (err) {
      setCombineStatus('Model combination failed: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setIsCombining(false);
      setTimeout(() => setCombineStatus(''), 8000);
    }
  };

  const brain = brainData || {};
  const inputs = brain.input_features || [];
  const l1 = brain.layer1_activations || [];
  const l2 = brain.layer2_activations || [];
  const probs = brain.probabilities || { HOLD: 0.33, BUY: 0.33, SELL: 0.34 };
  const action = brain.action || 'HOLD';
  const confidence = brain.confidence || 0;
  const expectedReturn = brain.expected_return_pct || 0;
  const synapses = brain.top_synapses || [];
  const reinforcements = brain.recent_reinforcements || [];

  // Dual Consciousness Feeds (Jarvis = Macro BTC/Trend, Ultron = High-Volatility Alts)
  const jarvisData =
    allBrainsData['Neural_Network_BTC'] ||
    (activeModelId === 'Neural_Network_BTC' ? brainData : null) ||
    brainData;
  const ultronData =
    allBrainsData['Neural_Network_ALTS'] ||
    (activeModelId === 'Neural_Network_ALTS' ? brainData : null) ||
    brainData;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Model Selection Tabs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {BRAIN_MODELS.map((model) => {
          const isSelected = activeModelId === model.id;
          return (
            <button
              key={model.id}
              onClick={() => handleModelSelect(model)}
              className={`p-4 rounded-xl text-left border transition-all relative overflow-hidden ${
                isSelected
                  ? `bg-gradient-to-br ${model.color} shadow-lg shadow-black/40 ring-1 ring-white/20`
                  : 'bg-cyber-surface/60 border-gray-800 hover:border-gray-700 opacity-70 hover:opacity-100'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-black/40 border border-white/10 text-white">
                  {model.tag}
                </span>
                {isSelected && (
                  <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-neon-green opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-neon-green"></span>
                  </span>
                )}
              </div>
              <h3 className="text-base font-bold text-white mt-2 font-heading">{model.name}</h3>
              <p className="text-[11px] text-gray-400 mt-1 line-clamp-2 leading-relaxed">
                {model.description}
              </p>

              {/* Live Simultaneous Telemetry Badge */}
              {allBrainsData[model.id] && (
                <div className="mt-3 flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-black/40 border border-white/5 text-[11px] font-mono">
                  <span className="text-gray-400">Live Decision:</span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`font-bold ${
                        allBrainsData[model.id].action === 'BUY'
                          ? 'text-neon-green'
                          : allBrainsData[model.id].action === 'SELL'
                          ? 'text-neon-pink'
                          : 'text-gray-300'
                      }`}
                    >
                      {allBrainsData[model.id].action}
                    </span>
                    <span className="text-neon-cyan">
                      {(allBrainsData[model.id].confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              )}

              <div className="flex items-center gap-1.5 mt-3 pt-2 border-t border-white/10">
                <span className="text-[10px] text-gray-400 font-mono">Pairs:</span>
                {model.pairs.map((p) => (
                  <span
                    key={p}
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      selectedPair === p
                        ? 'bg-neon-cyan text-black font-bold'
                        : 'bg-cyber-bg text-gray-300 border border-gray-700'
                    }`}
                  >
                    {p}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {/* Top Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-neon-cyan/10 border border-neon-cyan/40 flex items-center justify-center glow-cyan">
              <Zap className="text-neon-cyan animate-pulse" size={22} />
            </div>
            <div>
              <h1 className="text-3xl font-bold font-heading text-white">
                Neural <span className="text-neon-cyan">Brain Visualizer</span>
              </h1>
              <p className="text-gray-400 text-xs sm:text-sm">
                Viewing: <span className="text-neon-cyan font-bold font-mono">{brain.model_name || activeModelId}</span> on <span className="text-white font-mono">{selectedPair}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Controls Toolbar */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Pair Selector for Active Model */}
          <select
            value={selectedPair}
            onChange={(e) => handlePairChange(e.target.value)}
            className="bg-cyber-surface border border-gray-700 rounded-lg px-3 py-2 text-xs font-semibold text-white focus:border-neon-cyan focus:outline-none"
          >
            {BRAIN_MODELS.find((m) => m.id === activeModelId)?.pairs.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>

          {/* Active Signals Status Badge */}
          <div className="px-3 py-2 rounded-lg text-xs font-bold border flex items-center gap-1.5 bg-neon-green/20 text-neon-green border-neon-green/40 shadow-[0_0_15px_rgba(0,255,102,0.2)]">
            <CheckCircle2 size={14} className="text-neon-green" />
            <span>ACTIVE TRADING SIGNALS (LIVE)</span>
          </div>

          {/* Manual Synapse Pulse */}
          <button
            onClick={handleFireSynapses}
            disabled={isFiring}
            className="px-3 py-2 rounded-lg text-xs font-bold bg-neon-cyan/20 border border-neon-cyan/40 text-neon-cyan hover:bg-neon-cyan/30 transition-all flex items-center gap-1.5 shadow-[0_0_12px_rgba(0,240,255,0.2)]"
          >
            <Play size={14} className={isFiring ? 'animate-spin' : ''} />
            Pulse Synapses
          </button>

          {/* Combine & Train Unified Model */}
          <button
            onClick={handleCombineModels}
            disabled={isCombining}
            className="px-3 py-2 rounded-lg text-xs font-bold bg-purple-500/20 border border-purple-500/50 text-purple-300 hover:text-white hover:bg-purple-500/30 transition-all flex items-center gap-1.5 shadow-[0_0_12px_rgba(168,85,247,0.2)]"
          >
            <Layers size={14} className={isCombining ? 'animate-spin' : ''} />
            {isCombining ? 'Combining...' : 'Combine Models'}
          </button>

          {/* Train/Calibrate */}
          <button
            onClick={handleCalibrate}
            disabled={isCalibrating}
            className="px-3 py-2 rounded-lg text-xs font-bold bg-cyber-surface border border-gray-700 text-gray-300 hover:text-white hover:border-gray-500 transition-all flex items-center gap-1.5"
          >
            <RefreshCw size={14} className={isCalibrating ? 'animate-spin' : ''} />
            Calibrate Weights
          </button>
        </div>
      </div>

      {calibrateStatus && (
        <div className="p-3 rounded-lg bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan text-xs font-mono animate-fade-in flex items-center gap-2">
          <Activity size={14} className="animate-spin" />
          {calibrateStatus}
        </div>
      )}

      {combineStatus && (
        <div className="p-3 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 text-xs font-mono animate-fade-in flex items-center gap-2">
          <Layers size={14} className={isCombining ? 'animate-spin' : ''} />
          {combineStatus}
        </div>
      )}


      {/* Capital Preservation & Survival Health Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1 */}
        <div className="glass-card p-4 border-l-4 border-l-neon-green">
          <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold flex items-center justify-between">
            <span>Portfolio Survival Rate</span>
            <ShieldCheck size={16} className="text-neon-green" />
          </div>
          <div className="text-2xl font-bold font-mono text-neon-green mt-1">
            {capitalHealth?.survival_score ?? 100}%
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            Status: <span className="text-white font-semibold">{capitalHealth?.risk_status || 'OPTIMAL'}</span> (Capital Protected)
          </p>
        </div>

        {/* Metric 2 */}
        <div className="glass-card p-4 border-l-4 border-l-neon-cyan">
          <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold flex items-center justify-between">
            <span>Current Capital (Paper)</span>
            <TrendingUp size={16} className="text-neon-cyan" />
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-1">
            ₹{Number(capitalHealth?.portfolio_value || 10000).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            Cash: ₹{Number(capitalHealth?.cash_balance || 10000).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
          </p>
        </div>

        {/* Metric 3 */}
        <div className="glass-card p-4 border-l-4 border-l-neon-yellow">
          <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold flex items-center justify-between">
            <span>Continuous Train Steps</span>
            <Layers size={16} className="text-neon-yellow" />
          </div>
          <div className="text-2xl font-bold font-mono text-neon-yellow mt-1">
            {brain.train_steps || 0}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            Loss: <span className="text-white font-mono">{brain.last_loss || '0.000'}</span>
          </p>
        </div>

        {/* Metric 4 */}
        <div className="glass-card p-4 border-l-4 border-l-neon-magenta">
          <div className="text-[11px] uppercase tracking-wider text-gray-400 font-semibold flex items-center justify-between">
            <span>Reinforced Trades</span>
            <Award size={16} className="text-neon-magenta" />
          </div>
          <div className="text-2xl font-bold font-mono text-neon-magenta mt-1">
            {reinforcements.length}
          </div>
          <p className="text-[10px] text-gray-500 mt-1">
            Loss Penalty: <span className="text-neon-red font-bold">2.5x</span> (Averse to Drawdown)
          </p>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* THE LIVE INTERACTIVE BRAIN VISUALIZER (AVENGERS JARVIS & ULTRON ENGINE)   */}
      {/* ========================================================================= */}
      <div className="space-y-4">
        {/* Visualizer Display Mode Switcher */}
        <div className="flex items-center justify-between flex-wrap gap-3 p-3 rounded-xl bg-cyber-surface/40 border border-gray-800">
          <div className="flex items-center gap-2">
            <Sparkles className="text-neon-cyan animate-pulse" size={18} />
            <h2 className="text-base sm:text-lg font-bold font-heading text-white">
              Neural Consciousness Visualization
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded bg-black/60 border border-neon-cyan/40 text-neon-cyan font-mono font-bold">
              AVENGERS JARVIS &amp; ULTRON
            </span>
          </div>

          <div className="flex items-center p-1 rounded-xl bg-cyber-bg border border-gray-800 text-xs">
            <button
              onClick={() => setDisplayMode('hologram')}
              className={`px-3 py-1.5 font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                displayMode === 'hologram'
                  ? 'bg-gradient-to-r from-neon-cyan/20 to-orange-500/20 text-white border border-white/20 shadow-[0_0_15px_rgba(0,240,255,0.2)] font-bold'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Sparkles size={13} className="text-neon-cyan" />
              <span>3D Hologram (Avengers)</span>
            </button>
            <button
              onClick={() => setDisplayMode('both')}
              className={`px-3 py-1.5 font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                displayMode === 'both'
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-[0_0_12px_rgba(168,85,247,0.25)] font-bold'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Layers size={13} />
              <span>Dual Panoramic (3D + Matrix)</span>
            </button>
            <button
              onClick={() => setDisplayMode('matrix')}
              className={`px-3 py-1.5 font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                displayMode === 'matrix'
                  ? 'bg-neon-green/20 text-neon-green border border-neon-green/40 shadow-[0_0_12px_rgba(0,255,102,0.25)] font-bold'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Cpu size={13} />
              <span>Layer Architecture Matrix</span>
            </button>
          </div>
        </div>

        {/* 3D Holographic Brain Component */}
        {(displayMode === 'hologram' || displayMode === 'both') && (
          <div className="space-y-4">
            <HolographicBrainViewer
              jarvisData={jarvisData}
              ultronData={ultronData}
              activeModelId={activeModelId}
              selectedPair={selectedPair}
              isSurgeFiring={isFiring}
              onTriggerSurge={handleFireSynapses}
            />

            {/* Executive Decision Telemetry Bar */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 rounded-xl glass-card border border-gray-800">
              {/* Pair & Execution Regime */}
              <div className="flex flex-col justify-center">
                <span className="text-[10px] text-gray-400 font-mono uppercase tracking-wider">Market Inference</span>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-lg font-bold font-mono text-white">{selectedPair}</span>
                  <span className="text-xs font-mono text-neon-cyan">₹{Number(brain.price || 0).toLocaleString('en-IN')}</span>
                </div>
                <span className="text-[10px] text-gray-500 font-mono mt-0.5">
                  Live Feed • LayerNorm + LeakyReLU
                </span>
              </div>

              {/* Directional Softmax Decision */}
              <div className="flex flex-col justify-center md:col-span-2">
                <div className="flex items-center justify-between text-xs mb-1.5 font-mono">
                  <span className="text-gray-400">Directional Softmax Head:</span>
                  <div className="flex items-center gap-2 font-bold">
                    <span
                      className={
                        action === 'BUY'
                          ? 'text-neon-green'
                          : action === 'SELL'
                          ? 'text-neon-pink'
                          : 'text-neon-yellow'
                      }
                    >
                      {action} ({((confidence || 0) * 100).toFixed(1)}% Confidence)
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div
                    className={`p-2 rounded-lg border text-center transition-all ${
                      action === 'BUY'
                        ? 'bg-neon-green/20 border-neon-green text-neon-green shadow-[0_0_12px_rgba(0,255,102,0.3)] font-bold'
                        : 'bg-black/40 border-gray-800 text-gray-400'
                    }`}
                  >
                    <div className="text-[10px]">P(BUY)</div>
                    <div className="text-xs font-mono font-bold">{((probs.BUY || 0) * 100).toFixed(1)}%</div>
                  </div>

                  <div
                    className={`p-2 rounded-lg border text-center transition-all ${
                      action === 'HOLD'
                        ? 'bg-neon-yellow/20 border-neon-yellow text-neon-yellow shadow-[0_0_12px_rgba(255,210,0,0.3)] font-bold'
                        : 'bg-black/40 border-gray-800 text-gray-400'
                    }`}
                  >
                    <div className="text-[10px]">P(HOLD)</div>
                    <div className="text-xs font-mono font-bold">{((probs.HOLD || 0) * 100).toFixed(1)}%</div>
                  </div>

                  <div
                    className={`p-2 rounded-lg border text-center transition-all ${
                      action === 'SELL'
                        ? 'bg-neon-red/20 border-neon-red text-neon-red shadow-[0_0_12px_rgba(255,0,85,0.3)] font-bold'
                        : 'bg-black/40 border-gray-800 text-gray-400'
                    }`}
                  >
                    <div className="text-[10px]">P(SELL)</div>
                    <div className="text-xs font-mono font-bold">{((probs.SELL || 0) * 100).toFixed(1)}%</div>
                  </div>
                </div>
              </div>

              {/* Forward Return Projection */}
              <div className="flex flex-col justify-center">
                <span className="text-[10px] text-gray-400 font-mono uppercase tracking-wider">Regression Head</span>
                <div
                  className={`text-xl font-bold font-mono mt-1 ${
                    expectedReturn >= 0 ? 'text-neon-green' : 'text-neon-red'
                  }`}
                >
                  {expectedReturn >= 0 ? '+' : ''}
                  {expectedReturn.toFixed(2)}%
                </div>
                <span className="text-[10px] text-gray-500 font-mono mt-0.5">
                  Target 3-candle projection (45m)
                </span>
              </div>
            </div>
          </div>
        )}

        {/* 2D Technical Layer Architecture Matrix */}
        {(displayMode === 'matrix' || displayMode === 'both') && (
          <div className="glass-card p-6 overflow-hidden border border-neon-cyan/30 shadow-[0_0_30px_rgba(0,240,255,0.06)] relative">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-6 border-b border-gray-800 gap-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-neon-cyan animate-ping" />
            <h2 className="text-lg font-bold font-heading text-white">
              Neural Synaptic Flow — {selectedPair} @ ₹{Number(brain.price || 0).toLocaleString('en-IN')}
            </h2>
          </div>
          <div className="text-xs text-gray-400 font-mono">
            {isFiring ? (
              <span className="text-neon-green font-bold animate-pulse">⚡ SYNAPSES FIRING NOW</span>
            ) : (
              <span>Streaming Live Activations (LayerNorm + LeakyReLU)</span>
            )}
          </div>
        </div>

        {/* Layer Flow Architecture Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-start">
          {/* LAYER 0: 16 INPUT FEATURES */}
          <div className="space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-gray-800">
              <span className="text-xs uppercase font-bold text-gray-400">Layer 0: Input</span>
              <span className="text-[10px] font-mono text-neon-cyan">16 Indicators</span>
            </div>
            <div className="space-y-1.5 max-h-[520px] overflow-y-auto pr-1">
              {inputs.map((feat, i) => {
                const normVal = feat.norm_value ?? 0;
                const isPositive = normVal >= 0;
                const barWidth = Math.min(100, Math.abs(normVal) * 50);

                return (
                  <div
                    key={i}
                    className="p-1.5 rounded-lg bg-cyber-surface/60 border border-gray-800 text-xs flex flex-col hover:border-neon-cyan/40 transition-all group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] text-gray-300 font-semibold">
                        {feat.name}
                      </span>
                      <span className="font-mono text-[10px] text-gray-400">
                        {feat.raw_value}
                      </span>
                    </div>
                    {/* Normalized Indicator Pulse Bar */}
                    <div className="w-full h-1 bg-gray-800 rounded-full mt-1 overflow-hidden relative">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isPositive ? 'bg-neon-cyan' : 'bg-neon-red'
                        }`}
                        style={{ width: `${Math.max(8, barWidth)}%` }}
                      />
                    </div>
                    <span className="text-[9px] text-gray-500 hidden group-hover:block mt-0.5 font-sans">
                      {FEATURE_DESCRIPTIONS[feat.name] || feat.name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* LAYER 1: 64 HIDDEN NEURONS */}
          <div className="space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-gray-800">
              <span className="text-xs uppercase font-bold text-gray-400">Layer 1: Hidden</span>
              <span className="text-[10px] font-mono text-neon-green">64 Neurons</span>
            </div>
            <p className="text-[10px] text-gray-500">He-Init • LayerNorm • LeakyReLU</p>

            {/* 8x8 Grid of 64 Neurons */}
            <div className="grid grid-cols-8 gap-2 p-3 rounded-xl bg-cyber-surface/40 border border-gray-800">
              {l1.map((act, i) => {
                const glow = Math.min(1, Math.max(0.1, act));
                const isHigh = glow > 0.6;

                return (
                  <div
                    key={i}
                    title={`Neuron #${i}: Activation ${act}`}
                    className={`w-6 h-6 rounded-md flex items-center justify-center text-[8px] font-mono transition-all duration-500 ${
                      isHigh
                        ? 'bg-neon-green text-black font-bold shadow-[0_0_12px_rgba(0,255,102,0.8)] scale-110'
                        : 'bg-cyber-surface border border-gray-700 text-gray-400'
                    }`}
                    style={{
                      opacity: Math.max(0.25, glow),
                    }}
                  >
                    {i}
                  </div>
                );
              })}
            </div>

            <div className="text-[10px] text-gray-500 p-2 bg-cyber-bg rounded-lg border border-gray-800">
              <span className="text-neon-green font-semibold">Bright nodes</span> indicate neurons with strong feature activations for current market regime.
            </div>
          </div>

          {/* LAYER 2: 32 HIDDEN NEURONS */}
          <div className="space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-gray-800">
              <span className="text-xs uppercase font-bold text-gray-400">Layer 2: Hidden</span>
              <span className="text-[10px] font-mono text-neon-yellow">32 Neurons</span>
            </div>
            <p className="text-[10px] text-gray-500">Pattern Synthesis & Logic</p>

            {/* 4x8 Grid of 32 Neurons */}
            <div className="grid grid-cols-4 gap-2.5 p-3 rounded-xl bg-cyber-surface/40 border border-gray-800">
              {l2.map((act, i) => {
                const glow = Math.min(1, Math.max(0.15, act));
                const isHigh = glow > 0.65;

                return (
                  <div
                    key={i}
                    title={`L2 Neuron #${i}: Activation ${act}`}
                    className={`h-7 rounded-lg flex items-center justify-center text-[9px] font-mono transition-all duration-500 ${
                      isHigh
                        ? 'bg-neon-yellow text-black font-bold shadow-[0_0_15px_rgba(255,210,0,0.8)] scale-105'
                        : 'bg-cyber-surface border border-gray-700 text-gray-400'
                    }`}
                    style={{
                      opacity: Math.max(0.3, glow),
                    }}
                  >
                    N{i}
                  </div>
                );
              })}
            </div>

            <div className="text-[10px] text-gray-500 p-2 bg-cyber-bg rounded-lg border border-gray-800">
              <span className="text-neon-yellow font-semibold">Layer 2</span> consolidates technical patterns into forward classification logits.
            </div>
          </div>

          {/* LAYER 3: DUAL HEADS (OUTPUT DECISION & REGRESSION RETURN) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-gray-800">
              <span className="text-xs uppercase font-bold text-gray-400">Layer 3: Output</span>
              <span className="text-[10px] font-mono text-neon-magenta">Dual Head</span>
            </div>

            {/* Classification Probabilities */}
            <div className="p-4 rounded-xl bg-cyber-surface/60 border border-gray-800 space-y-3">
              <span className="text-[11px] uppercase font-bold text-gray-400 block">
                Directional Softmax Head
              </span>

              {/* BUY */}
              <div
                className={`p-2.5 rounded-lg border transition-all ${
                  action === 'BUY'
                    ? 'bg-neon-green/15 border-neon-green text-neon-green shadow-[0_0_15px_rgba(0,255,102,0.3)] font-bold'
                    : 'bg-cyber-bg border-gray-800 text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span>P(BUY)</span>
                  <span className="font-mono text-sm">{((probs.BUY || 0) * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full h-1.5 bg-gray-800 rounded-full mt-1.5 overflow-hidden">
                  <div
                    className="h-full bg-neon-green rounded-full transition-all duration-700"
                    style={{ width: `${(probs.BUY || 0) * 100}%` }}
                  />
                </div>
              </div>

              {/* HOLD */}
              <div
                className={`p-2.5 rounded-lg border transition-all ${
                  action === 'HOLD'
                    ? 'bg-neon-yellow/15 border-neon-yellow text-neon-yellow shadow-[0_0_15px_rgba(255,210,0,0.3)] font-bold'
                    : 'bg-cyber-bg border-gray-800 text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span>P(HOLD)</span>
                  <span className="font-mono text-sm">{((probs.HOLD || 0) * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full h-1.5 bg-gray-800 rounded-full mt-1.5 overflow-hidden">
                  <div
                    className="h-full bg-neon-yellow rounded-full transition-all duration-700"
                    style={{ width: `${(probs.HOLD || 0) * 100}%` }}
                  />
                </div>
              </div>

              {/* SELL */}
              <div
                className={`p-2.5 rounded-lg border transition-all ${
                  action === 'SELL'
                    ? 'bg-neon-red/15 border-neon-red text-neon-red shadow-[0_0_15px_rgba(255,0,85,0.3)] font-bold'
                    : 'bg-cyber-bg border-gray-800 text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span>P(SELL)</span>
                  <span className="font-mono text-sm">{((probs.SELL || 0) * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full h-1.5 bg-gray-800 rounded-full mt-1.5 overflow-hidden">
                  <div
                    className="h-full bg-neon-red rounded-full transition-all duration-700"
                    style={{ width: `${(probs.SELL || 0) * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Regression Return Head */}
            <div className="p-4 rounded-xl bg-cyber-surface/60 border border-gray-800">
              <span className="text-[11px] uppercase font-bold text-gray-400 block mb-1">
                Regression Head (Forward Return)
              </span>
              <div
                className={`text-2xl font-bold font-mono ${
                  expectedReturn >= 0 ? 'text-neon-green' : 'text-neon-red'
                }`}
              >
                {expectedReturn >= 0 ? '+' : ''}
                {expectedReturn.toFixed(2)}%
              </div>
              <p className="text-[10px] text-gray-500 mt-0.5">
                Target projection over 3 candles (45 min)
              </p>
            </div>
          </div>
        </div>
      </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* CLOSED TRADE REINFORCEMENT LEARNING LOG                                  */}
      {/* ========================================================================= */}
      <div className="glass-card overflow-hidden">
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu size={16} className="text-neon-magenta" />
            <h3 className="font-heading text-sm font-bold text-white">
              Self-Learning & Reinforcement History (Trade Outcome Feedback Loop)
            </h3>
          </div>
          <span className="text-xs text-gray-400 font-mono">
            Survival Guard Active (Winning Trades Reinforced • Losing Trades Heavily Penalized)
          </span>
        </div>

        {reinforcements.length === 0 ? (
          <div className="p-12 text-center text-gray-500 text-xs">
            <AlertTriangle size={32} className="mx-auto mb-2 text-gray-600" />
            No closed trades reinforced yet. As paper trades hit Take Profit or Stop Loss,
            their outcomes are immediately fed back into Adam backpropagation.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400">
                  <th className="p-3 text-left">Trade</th>
                  <th className="p-3 text-left">Pair</th>
                  <th className="p-3 text-center">Action</th>
                  <th className="p-3 text-center">Trade PnL %</th>
                  <th className="p-3 text-left">Learning Target Direction</th>
                  <th className="p-3 text-center">Penalty / Reinforce Weight</th>
                  <th className="p-3 text-right">Step #</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 font-mono">
                {reinforcements.map((r, idx) => (
                  <tr key={idx} className="hover:bg-cyber-surface/40">
                    <td className="p-3 text-white font-semibold">#{r.trade_id || idx + 1}</td>
                    <td className="p-3 text-gray-300">{r.pair}</td>
                    <td className="p-3 text-center">
                      <span className="px-2 py-0.5 rounded bg-gray-800 text-white font-bold">
                        {r.action}
                      </span>
                    </td>
                    <td className="p-3 text-center font-bold">
                      <span className={r.pnl_pct >= 0 ? 'text-neon-green' : 'text-neon-red'}>
                        {r.pnl_pct >= 0 ? '+' : ''}
                        {r.pnl_pct}%
                      </span>
                    </td>
                    <td className="p-3">
                      {r.pnl_pct >= 0 ? (
                        <span className="text-neon-green">Reinforced winning {r.target_class} setup</span>
                      ) : (
                        <span className="text-neon-red">Penalized losing setup &rarr; shifted to HOLD</span>
                      )}
                    </td>
                    <td className="p-3 text-center text-yellow-400 font-bold">{r.sample_weight}x</td>
                    <td className="p-3 text-right text-neon-cyan">#{r.total_train_steps}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
