import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';

export default function PaperLiveToggle({ mode = 'paper', onToggle, disabled = false }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const isPaper = mode === 'paper';

  // Handle ESC key to dismiss modal
  useEffect(() => {
    if (!showConfirm) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowConfirm(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showConfirm]);

  const handleClick = () => {
    if (disabled) return;
    if (isPaper) {
      // Switching to Live — show confirmation
      setShowConfirm(true);
    } else {
      // Switching to Paper — no confirmation needed
      onToggle?.('paper');
    }
  };

  const confirmLive = () => {
    setShowConfirm(false);
    onToggle?.('live');
  };

  return (
    <>
      {/* Toggle */}
      <button
        onClick={handleClick}
        disabled={disabled}
        className={`relative flex items-center gap-2 rounded-full px-1 py-1 transition-all duration-300 ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
        } ${
          isPaper
            ? 'bg-neon-cyan/10 border border-neon-cyan/30'
            : 'bg-neon-red/10 border border-neon-red/30'
        }`}
        style={{ width: '140px' }}
      >
        {/* Sliding background */}
        <div
          className={`absolute top-1 h-[calc(100%-8px)] w-[64px] rounded-full transition-all duration-300 ease-in-out ${
            isPaper
              ? 'left-1 bg-neon-cyan/20 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
              : 'left-[calc(100%-68px)] bg-neon-red/20 shadow-[0_0_12px_rgba(255,51,102,0.3)]'
          }`}
        />

        {/* Paper label */}
        <span
          className={`relative z-10 px-3 py-0.5 text-xs font-heading font-bold uppercase tracking-wider transition-all duration-300 ${
            isPaper ? 'text-neon-cyan' : 'text-gray-500'
          }`}
        >
          Paper
        </span>

        {/* Live label */}
        <span
          className={`relative z-10 px-3 py-0.5 text-xs font-heading font-bold uppercase tracking-wider transition-all duration-300 ${
            !isPaper ? 'text-neon-red' : 'text-gray-500'
          }`}
        >
          Live
        </span>
      </button>

      {/* Confirmation Modal rendered via Portal to escape header backdrop-filter containing block */}
      {showConfirm && typeof document !== 'undefined' && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in overflow-y-auto">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/80 backdrop-blur-md"
            onClick={() => setShowConfirm(false)}
          />

          {/* Modal Card - centrally positioned in viewport */}
          <div className="relative glass-card p-6 sm:p-7 max-w-md w-full mx-auto my-auto rounded-2xl border border-neon-red/40 shadow-[0_0_50px_rgba(255,51,102,0.25)] animate-slide-in z-10 bg-cyber-card/95">
            <button
              onClick={() => setShowConfirm(false)}
              className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/10 transition-colors"
              aria-label="Close dialog"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3.5 mb-4">
              <div className="w-12 h-12 rounded-xl bg-neon-red/15 border border-neon-red/30 flex items-center justify-center flex-shrink-0 text-neon-red shadow-[0_0_15px_rgba(255,51,102,0.3)]">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-lg font-heading font-bold text-white tracking-wide">
                  Switch to Live Mode?
                </h3>
                <p className="text-xs text-gray-400">
                  Real funds & active exchange orders
                </p>
              </div>
            </div>

            <div className="bg-neon-red/10 border border-neon-red/30 rounded-xl p-4 mb-6">
              <p className="text-sm text-gray-200 leading-relaxed">
                <span className="text-neon-red font-bold">⚠ Warning:</span> Live mode executes orders with{' '}
                <span className="text-neon-red font-bold underline">REAL money</span> on CoinDCX.
                Verify your API keys, balance, and risk thresholds before proceeding.
              </p>
            </div>

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                className="flex-1 btn-neon py-2.5 font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmLive}
                className="flex-1 btn-danger py-2.5 font-bold shadow-[0_0_20px_rgba(255,51,102,0.4)]"
              >
                Enable Live Mode
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
