import { useState, useEffect } from 'react';
import { Settings2, Save, Check, ToggleLeft, ToggleRight, ChevronDown, ChevronUp } from 'lucide-react';
import { getStrategies, updateStrategy } from '../utils/api';

const strategyDescriptions = {
  'ma_pullback': 'Uses EMA 9/21/50 crossover with StochRSI confirmation. Buys on pullback to EMA21 when oversold.',
  'breakout_hunter': 'Detects Bollinger Band squeezes and enters on breakout above upper band with volume confirmation.',
  'rsi_divergence': 'Identifies bullish/bearish divergence between price action and RSI on 15m and 1h timeframes.',
  'sentiment_llm': 'AI-powered analysis using local Ollama LLM. Evaluates market data and provides high-confidence signals.',
  'grid_trading': 'Places automated buy/sell grid orders around current price. Auto-rebalances when price exits range.',
};

const strategyIcons = {
  'ma_pullback': '📈',
  'breakout_hunter': '🚀',
  'rsi_divergence': '🔀',
  'sentiment_llm': '🧠',
  'grid_trading': '📊',
};

const paramLabels = {
  ema_fast: 'Fast EMA Period',
  ema_mid: 'Mid EMA Period',
  ema_slow: 'Slow EMA Period',
  stoch_rsi_buy: 'StochRSI Buy Level',
  stoch_rsi_sell: 'StochRSI Sell Level',
  profit_target_pct: 'Profit Target %',
  bb_period: 'Bollinger Period',
  bb_std: 'Bollinger Std Dev',
  squeeze_threshold: 'Squeeze Threshold',
  volume_multiplier: 'Volume Multiplier',
  rsi_period: 'RSI Period',
  swing_window: 'Swing Window',
  min_divergence_bars: 'Min Divergence Bars',
  confidence_threshold: 'Confidence Threshold',
  model: 'LLM Model',
  fallback_model: 'Fallback Model',
  grid_spacing_pct: 'Grid Spacing %',
  num_levels: 'Grid Levels',
  capital_per_grid: 'Capital Per Grid (₹)',
  rebalance_threshold_pct: 'Rebalance Threshold %',
};

export default function StrategyConfig() {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedCards, setExpandedCards] = useState({});
  const [editedParams, setEditedParams] = useState({});
  const [saving, setSaving] = useState({});
  const [saved, setSaved] = useState({});

  useEffect(() => {
    fetchStrategies();
  }, []);

  const fetchStrategies = async () => {
    try {
      const res = await getStrategies();
      const raw = res.data?.strategies || {};
      // Backend returns an object keyed by strategy name; convert to an array for rendering.
      const list = Array.isArray(raw) ? raw : Object.values(raw);
      setStrategies(list);
    } catch (err) {
      console.error('Failed to fetch strategies:', err);
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (name) => {
    setExpandedCards(prev => ({ ...prev, [name]: !prev[name] }));
  };

  const handleToggle = async (strategy) => {
    const newEnabled = !strategy.enabled;
    try {
      await updateStrategy(strategy.name, { enabled: newEnabled, params: strategy.params });
      setStrategies(prev =>
        prev.map(s => s.name === strategy.name ? { ...s, enabled: newEnabled } : s)
      );
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  };

  const handleParamChange = (stratName, paramKey, value) => {
    setEditedParams(prev => ({
      ...prev,
      [stratName]: {
        ...(prev[stratName] || {}),
        [paramKey]: value,
      },
    }));
  };

  const handleSave = async (strategy) => {
    setSaving(prev => ({ ...prev, [strategy.name]: true }));
    try {
      const updatedParams = {
        ...strategy.params,
        ...(editedParams[strategy.name] || {}),
      };
      // Convert numeric strings to numbers
      Object.keys(updatedParams).forEach(k => {
        const v = updatedParams[k];
        if (typeof v === 'string' && !isNaN(v) && v !== '') {
          updatedParams[k] = parseFloat(v);
        }
      });
      await updateStrategy(strategy.name, { enabled: strategy.enabled, params: updatedParams });
      setStrategies(prev =>
        prev.map(s => s.name === strategy.name ? { ...s, params: updatedParams } : s)
      );
      setEditedParams(prev => ({ ...prev, [strategy.name]: {} }));
      setSaved(prev => ({ ...prev, [strategy.name]: true }));
      setTimeout(() => setSaved(prev => ({ ...prev, [strategy.name]: false })), 2000);
    } catch (err) {
      console.error('Save failed:', err);
    } finally {
      setSaving(prev => ({ ...prev, [strategy.name]: false }));
    }
  };

  const getParamValue = (stratName, paramKey, defaultValue) => {
    return editedParams[stratName]?.[paramKey] ?? defaultValue;
  };

  const hasEdits = (stratName) => {
    const edits = editedParams[stratName];
    return edits && Object.keys(edits).length > 0;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold font-heading text-white">
          Strategy <span className="text-neon-cyan">Configuration</span>
        </h1>
        <p className="text-gray-400 mt-1">Enable, disable, and fine-tune your trading strategies</p>
      </div>

      {/* Strategy Cards */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="h-48 glass-card animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {strategies.map(strategy => (
            <div
              key={strategy.name}
              className={`glass-card overflow-hidden transition-all duration-500 
                ${strategy.enabled 
                  ? 'border-neon-cyan/30 shadow-[0_0_20px_rgba(0,240,255,0.08)]' 
                  : 'border-gray-800 opacity-75'}`}
            >
              {/* Card Header */}
              <div className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{strategyIcons[strategy.name] || '⚡'}</span>
                    <div>
                      <h3 className="text-lg font-heading font-bold text-white capitalize">
                        {strategy.name.replace(/_/g, ' ')}
                      </h3>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {strategyDescriptions[strategy.name] || 'Custom trading strategy'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleToggle(strategy)}
                    className="transition-transform duration-300 hover:scale-110"
                  >
                    {strategy.enabled ? (
                      <ToggleRight size={36} className="text-neon-cyan" />
                    ) : (
                      <ToggleLeft size={36} className="text-gray-600" />
                    )}
                  </button>
                </div>

                {/* Status Badge */}
                <div className="flex items-center gap-2 mt-2">
                  <div className={`w-2 h-2 rounded-full ${strategy.enabled ? 'bg-neon-green animate-pulse' : 'bg-gray-600'}`} />
                  <span className={`text-xs font-medium ${strategy.enabled ? 'text-neon-green' : 'text-gray-600'}`}>
                    {strategy.enabled ? 'Active' : 'Disabled'}
                  </span>
                </div>
              </div>

              {/* Expand/Collapse */}
              <button
                onClick={() => toggleExpand(strategy.name)}
                className="w-full px-5 py-3 border-t border-cyber-surface flex items-center justify-between
                           text-sm text-gray-400 hover:text-neon-cyan hover:bg-cyber-surface/30 transition-all"
              >
                <span className="flex items-center gap-2">
                  <Settings2 size={14} />
                  Parameters ({Object.keys(strategy.params || {}).length})
                </span>
                {expandedCards[strategy.name] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>

              {/* Parameters Section */}
              {expandedCards[strategy.name] && (
                <div className="px-5 pb-5 border-t border-cyber-surface/50 animate-slide-in">
                  <div className="space-y-3 mt-4">
                    {Object.entries(strategy.params || {}).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between gap-4">
                        <label className="text-sm text-gray-400 min-w-0 flex-shrink">
                          {paramLabels[key] || key.replace(/_/g, ' ')}
                        </label>
                        <input
                          type={typeof value === 'number' ? 'number' : 'text'}
                          value={getParamValue(strategy.name, key, value)}
                          onChange={(e) => handleParamChange(strategy.name, key, e.target.value)}
                          step={typeof value === 'number' && value < 1 ? '0.01' : '1'}
                          className="w-32 bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm 
                                     text-white text-right font-mono focus:border-neon-cyan/50 focus:outline-none
                                     focus:shadow-[0_0_10px_rgba(0,240,255,0.1)] transition-all"
                        />
                      </div>
                    ))}
                  </div>

                  {/* Save Button */}
                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={() => handleSave(strategy)}
                      disabled={saving[strategy.name] || !hasEdits(strategy.name)}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300
                        ${saved[strategy.name]
                          ? 'bg-neon-green/20 text-neon-green border border-neon-green/30'
                          : hasEdits(strategy.name)
                            ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30 hover:bg-neon-cyan/30 hover:shadow-[0_0_15px_rgba(0,240,255,0.2)]'
                            : 'bg-cyber-surface text-gray-600 border border-gray-800 cursor-not-allowed'}`}
                    >
                      {saved[strategy.name] ? (
                        <><Check size={16} /> Saved</>
                      ) : saving[strategy.name] ? (
                        <><RefreshCw size={16} className="animate-spin" /> Saving...</>
                      ) : (
                        <><Save size={16} /> Save Changes</>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RefreshCw(props) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={props.className}>
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </svg>
  );
}
