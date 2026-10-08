import { useState, useEffect } from 'react';
import { Shield, Save, Check, AlertTriangle, RefreshCw } from 'lucide-react';
import { getRiskSettings, updateRiskSettings } from '../utils/api';

export default function RiskSettings() {
  const [settings, setSettings] = useState({
    max_position_pct: 5,
    max_open_trades: 5,
    daily_loss_limit_pct: 3,
    default_stop_loss_pct: 1.5,
    default_take_profit_pct: 3.0,
    trailing_stop_activate_pct: 1.5,
    trailing_stop_trail_pct: 0.5,
  });
  const [original, setOriginal] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await getRiskSettings();
      const data = res.data || {};
      setSettings(data);
      setOriginal(data);
    } catch (err) {
      setError('Failed to load risk settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateRiskSettings(settings);
      setOriginal({ ...settings });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(original);

  const updateSetting = (key, value) => {
    setSettings(prev => ({ ...prev, [key]: parseFloat(value) || 0 }));
  };

  const riskLevel = () => {
    const score = settings.max_position_pct * 2 + (10 - settings.daily_loss_limit_pct) + (5 - settings.default_stop_loss_pct) * 3;
    if (score > 25) return { label: 'Aggressive', color: 'neon-red', bar: 90 };
    if (score > 15) return { label: 'Moderate', color: 'neon-yellow', bar: 60 };
    return { label: 'Conservative', color: 'neon-green', bar: 30 };
  };

  const risk = riskLevel();

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="h-10 w-64 bg-cyber-surface/50 rounded animate-pulse" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-32 glass-card animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white">
            Risk <span className="text-neon-cyan">Settings</span>
          </h1>
          <p className="text-gray-400 mt-1">Configure position sizing, stop losses, and risk limits</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !hasChanges}
          className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-all duration-300
            ${saved
              ? 'bg-neon-green/20 text-neon-green border border-neon-green/30'
              : hasChanges
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30 hover:bg-neon-cyan/30 hover:shadow-[0_0_20px_rgba(0,240,255,0.2)]'
                : 'bg-cyber-surface text-gray-600 border border-gray-800 cursor-not-allowed'}`}
        >
          {saved ? <><Check size={18} /> Saved!</> :
           saving ? <><RefreshCw size={18} className="animate-spin" /> Saving...</> :
           <><Save size={18} /> Save Settings</>}
        </button>
      </div>

      {error && (
        <div className="glass-card border-neon-red/30 p-4 flex items-center gap-3">
          <AlertTriangle className="text-neon-red" size={20} />
          <span className="text-neon-red">{error}</span>
        </div>
      )}

      {/* Risk Level Indicator */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Shield className={`text-${risk.color}`} size={24} />
            <div>
              <h3 className="text-lg font-heading text-white">Risk Profile</h3>
              <p className={`text-sm font-semibold text-${risk.color}`}>{risk.label}</p>
            </div>
          </div>
        </div>
        <div className="h-3 bg-cyber-surface rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 bg-${risk.color}`}
            style={{ width: `${risk.bar}%` }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-600">
          <span>Conservative</span>
          <span>Moderate</span>
          <span>Aggressive</span>
        </div>
      </div>

      {/* Settings Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Position Sizing */}
        <div className="glass-card p-6 group hover:border-neon-cyan/20 transition-all duration-300">
          <h3 className="text-lg font-heading text-white mb-6 flex items-center gap-2">
            📊 Position Sizing
          </h3>

          {/* Max Position Size - Slider */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-400">Max Position Size</label>
              <span className="text-lg font-bold font-mono text-neon-cyan">{settings.max_position_pct}%</span>
            </div>
            <input
              type="range"
              min="1"
              max="20"
              step="0.5"
              value={settings.max_position_pct}
              onChange={e => updateSetting('max_position_pct', e.target.value)}
              className="w-full h-2 bg-cyber-surface rounded-full appearance-none cursor-pointer
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 
                         [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full 
                         [&::-webkit-slider-thumb]:bg-neon-cyan [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(0,240,255,0.5)]
                         [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>1%</span>
              <span>10%</span>
              <span>20%</span>
            </div>
          </div>

          {/* Max Open Trades */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-400">Max Open Trades</label>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => updateSetting('max_open_trades', Math.max(1, settings.max_open_trades - 1))}
                  className="w-8 h-8 rounded-lg bg-cyber-surface border border-gray-700 text-gray-400 
                             hover:border-neon-cyan/30 hover:text-neon-cyan transition-all flex items-center justify-center"
                >
                  −
                </button>
                <span className="text-lg font-bold font-mono text-neon-cyan w-8 text-center">
                  {settings.max_open_trades}
                </span>
                <button
                  onClick={() => updateSetting('max_open_trades', Math.min(20, settings.max_open_trades + 1))}
                  className="w-8 h-8 rounded-lg bg-cyber-surface border border-gray-700 text-gray-400 
                             hover:border-neon-cyan/30 hover:text-neon-cyan transition-all flex items-center justify-center"
                >
                  +
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Daily Limits */}
        <div className="glass-card p-6 group hover:border-neon-cyan/20 transition-all duration-300">
          <h3 className="text-lg font-heading text-white mb-6 flex items-center gap-2">
            🛑 Daily Limits
          </h3>

          {/* Daily Loss Limit - Slider */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-gray-400">Daily Loss Limit</label>
              <span className="text-lg font-bold font-mono text-neon-red">{settings.daily_loss_limit_pct}%</span>
            </div>
            <input
              type="range"
              min="1"
              max="10"
              step="0.5"
              value={settings.daily_loss_limit_pct}
              onChange={e => updateSetting('daily_loss_limit_pct', e.target.value)}
              className="w-full h-2 bg-cyber-surface rounded-full appearance-none cursor-pointer
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 
                         [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full 
                         [&::-webkit-slider-thumb]:bg-neon-red [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(255,51,102,0.5)]
                         [&::-webkit-slider-thumb]:cursor-pointer"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-1">
              <span>1%</span>
              <span>5%</span>
              <span>10%</span>
            </div>
          </div>

          <p className="text-xs text-gray-600 bg-cyber-surface/50 rounded-lg p-3">
            ⚠️ Bot will automatically stop trading for the day if portfolio drops by this percentage.
          </p>
        </div>

        {/* Stop Loss & Take Profit */}
        <div className="glass-card p-6 group hover:border-neon-cyan/20 transition-all duration-300">
          <h3 className="text-lg font-heading text-white mb-6 flex items-center gap-2">
            🎯 Stop Loss & Take Profit
          </h3>

          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-gray-400">Default Stop Loss</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={settings.default_stop_loss_pct}
                    onChange={e => updateSetting('default_stop_loss_pct', e.target.value)}
                    step="0.1"
                    min="0.5"
                    max="5"
                    className="w-20 bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm 
                               text-neon-red text-right font-mono focus:border-neon-red/50 focus:outline-none transition-all"
                  />
                  <span className="text-sm text-gray-500">%</span>
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-gray-400">Default Take Profit</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={settings.default_take_profit_pct}
                    onChange={e => updateSetting('default_take_profit_pct', e.target.value)}
                    step="0.1"
                    min="1"
                    max="10"
                    className="w-20 bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm 
                               text-neon-green text-right font-mono focus:border-neon-green/50 focus:outline-none transition-all"
                  />
                  <span className="text-sm text-gray-500">%</span>
                </div>
              </div>
            </div>

            {/* Visual Risk/Reward */}
            <div className="bg-cyber-surface/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-2">Risk/Reward Ratio</div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-3 bg-neon-red/20 rounded-l-full overflow-hidden">
                  <div className="h-full bg-neon-red/60 rounded-l-full" style={{ width: `${(settings.default_stop_loss_pct / (settings.default_stop_loss_pct + settings.default_take_profit_pct)) * 100}%` }} />
                </div>
                <span className="text-xs font-mono text-gray-400 flex-shrink-0">
                  1:{(settings.default_take_profit_pct / settings.default_stop_loss_pct).toFixed(1)}
                </span>
                <div className="flex-1 h-3 bg-neon-green/20 rounded-r-full overflow-hidden flex justify-end">
                  <div className="h-full bg-neon-green/60 rounded-r-full" style={{ width: `${(settings.default_take_profit_pct / (settings.default_stop_loss_pct + settings.default_take_profit_pct)) * 100}%` }} />
                </div>
              </div>
              <div className="flex justify-between text-xs mt-1">
                <span className="text-neon-red/70">Risk</span>
                <span className="text-neon-green/70">Reward</span>
              </div>
            </div>
          </div>
        </div>

        {/* Trailing Stop */}
        <div className="glass-card p-6 group hover:border-neon-cyan/20 transition-all duration-300">
          <h3 className="text-lg font-heading text-white mb-6 flex items-center gap-2">
            📈 Trailing Stop
          </h3>

          <div className="space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-gray-400">Activate After Profit</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={settings.trailing_stop_activate_pct}
                    onChange={e => updateSetting('trailing_stop_activate_pct', e.target.value)}
                    step="0.1"
                    min="0.5"
                    max="5"
                    className="w-20 bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm 
                               text-neon-yellow text-right font-mono focus:border-neon-yellow/50 focus:outline-none transition-all"
                  />
                  <span className="text-sm text-gray-500">%</span>
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-gray-400">Trail Distance</label>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={settings.trailing_stop_trail_pct}
                    onChange={e => updateSetting('trailing_stop_trail_pct', e.target.value)}
                    step="0.1"
                    min="0.1"
                    max="3"
                    className="w-20 bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm 
                               text-neon-yellow text-right font-mono focus:border-neon-yellow/50 focus:outline-none transition-all"
                  />
                  <span className="text-sm text-gray-500">%</span>
                </div>
              </div>
            </div>

            <div className="bg-cyber-surface/50 rounded-lg p-3 text-xs text-gray-500">
              💡 Trailing stop activates once profit reaches {settings.trailing_stop_activate_pct}%, 
              then trails {settings.trailing_stop_trail_pct}% behind the highest price reached.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
