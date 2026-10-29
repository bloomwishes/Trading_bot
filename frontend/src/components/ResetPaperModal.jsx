import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { RotateCcw, Brain, Trash2, AlertTriangle, CheckCircle2, Loader2, X, ShieldAlert } from 'lucide-react';
import { resetPaperAccount } from '../utils/api';
import { formatINR } from '../utils/formatters';

export default function ResetPaperModal({ isOpen, onClose, onSuccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  if (!isOpen) return null;

  const handleReset = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await resetPaperAccount();
      setResult(res.data);
      if (onSuccess) {
        onSuccess(res.data);
      }
    } catch (err) {
      console.error('Failed to reset paper account:', err);
      const detail = err?.response?.data?.detail || err?.message || 'Failed to reset paper account';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const handleDone = () => {
    setResult(null);
    setError(null);
    onClose();
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg p-6 glass-card border-neon-purple/40 shadow-[0_0_50px_rgba(180,0,255,0.25)] rounded-2xl bg-cyber-bg/95">
        {/* Close Button */}
        <button
          onClick={result ? handleDone : onClose}
          disabled={loading}
          className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <X size={20} />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-11 h-11 rounded-xl bg-neon-purple/15 border border-neon-purple/40 flex items-center justify-center text-neon-purple shadow-[0_0_20px_rgba(180,0,255,0.3)]">
            <Brain size={24} className={loading ? "animate-pulse" : ""} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold font-heading text-white">Reset Paper Trading</h2>
              <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider bg-neon-purple/20 text-neon-purple border border-neon-purple/40 rounded-full uppercase">
                Paper Mode Only
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              Train neural network on trade history, purge records & restore capital
            </p>
          </div>
        </div>

        {/* Success View */}
        {result ? (
          <div className="space-y-4 my-2">
            <div className="p-4 rounded-xl bg-neon-green/10 border border-neon-green/30 text-neon-green text-sm flex items-start gap-3">
              <CheckCircle2 size={20} className="shrink-0 mt-0.5 text-neon-green" />
              <div>
                <p className="font-semibold text-white">Paper Account Reset & Calibrated!</p>
                <p className="text-xs text-neon-green/90 mt-1">{result.message}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-cyber-surface/60 border border-white/5">
                <span className="text-gray-400 block mb-1">Trades Trained</span>
                <span className="font-mono text-base font-bold text-neon-cyan">
                  {result.trained_trades ?? 0}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-cyber-surface/60 border border-white/5">
                <span className="text-gray-400 block mb-1">Active Closed</span>
                <span className="font-mono text-base font-bold text-neon-yellow">
                  {result.closed_active_trades ?? 0}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-cyber-surface/60 border border-white/5">
                <span className="text-gray-400 block mb-1">History Purged</span>
                <span className="font-mono text-base font-bold text-neon-magenta">
                  {result.purged_records ?? 0} records
                </span>
              </div>
              <div className="p-3 rounded-lg bg-cyber-surface/60 border border-white/5">
                <span className="text-gray-400 block mb-1">Reset Balance</span>
                <span className="font-mono text-base font-bold text-neon-green">
                  {formatINR(result.current_balance || 10000)}
                </span>
              </div>
            </div>

            <button
              onClick={handleDone}
              className="w-full mt-4 py-2.5 rounded-xl font-heading font-bold text-sm bg-neon-green text-black hover:shadow-[0_0_20px_rgba(0,255,136,0.4)] transition-all"
            >
              Done
            </button>
          </div>
        ) : (
          /* Confirmation Content */
          <div className="space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-neon-red/10 border border-neon-red/30 text-neon-red text-xs flex items-center gap-2">
                <AlertTriangle size={16} className="shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-2.5 text-xs text-gray-300">
              <p className="text-gray-400">
                Confirming will execute the following automated sequence in a single transaction:
              </p>

              <div className="p-3 rounded-xl bg-cyber-surface/50 border border-white/5 space-y-2">
                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-neon-purple/20 text-neon-purple flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">1</div>
                  <div>
                    <span className="font-semibold text-white">Close Active Trades: </span>
                    <span className="text-gray-400">Instantly liquidates all open paper positions at live market prices to lock in final PnL.</span>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-neon-cyan/20 text-neon-cyan flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">2</div>
                  <div>
                    <span className="font-semibold text-white">Train Neural Network: </span>
                    <span className="text-gray-400">Feeds all historical & newly closed trade results to calibrate neural models (reinforcing wins, penalizing losses).</span>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-neon-magenta/20 text-neon-magenta flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">3</div>
                  <div>
                    <span className="font-semibold text-white">Delete Trade History: </span>
                    <span className="text-gray-400">Purges all paper trade records and historical snapshots from the database.</span>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-neon-green/20 text-neon-green flex items-center justify-center shrink-0 mt-0.5 text-[10px] font-bold">4</div>
                  <div>
                    <span className="font-semibold text-white">Reset Starting Capital: </span>
                    <span className="text-gray-400">Restores portfolio cash balance back to starting capital (<strong className="text-neon-green font-mono">₹10,000.00</strong>).</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-400 hover:text-white bg-white/5 hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={loading}
                className="px-5 py-2.5 rounded-xl text-xs font-heading font-bold text-white bg-neon-purple hover:bg-neon-purple/90 shadow-[0_0_20px_rgba(180,0,255,0.4)] flex items-center gap-2 transition-all disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Training AI & Resetting...</span>
                  </>
                ) : (
                  <>
                    <RotateCcw size={14} />
                    <span>Reset & Train Neural Net</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
