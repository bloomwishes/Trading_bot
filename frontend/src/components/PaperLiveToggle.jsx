import React, { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function PaperLiveToggle({ mode = 'paper', onToggle, disabled = false }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const isPaper = mode === 'paper';

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

      {/* Confirmation Modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center animate-fade-in">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setShowConfirm(false)}
          />

          {/* Modal */}
          <div className="relative glass-card p-6 max-w-md w-full mx-4 border border-neon-red/30 animate-slide-in">
            <button
              onClick={() => setShowConfirm(false)}
              className="absolute top-4 right-4 text-gray-500 hover:text-gray-300 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-neon-red/10 border border-neon-red/30 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-neon-red" />
              </div>
              <div>
                <h3 className="text-lg font-heading font-bold text-white">Switch to Live Mode?</h3>
                <p className="text-sm text-gray-400">This action requires confirmation</p>
              </div>
            </div>

            <div className="bg-neon-red/5 border border-neon-red/20 rounded-lg p-4 mb-6">
              <p className="text-sm text-gray-300 leading-relaxed">
                <span className="text-neon-red font-semibold">⚠ Warning:</span> Live mode uses{' '}
                <span className="text-neon-red font-bold">REAL money</span> for trading. Ensure your
                risk settings are properly configured before proceeding. All trades will be executed
                on the live exchange.
              </p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="flex-1 btn-neon"
              >
                Cancel
              </button>
              <button
                onClick={confirmLive}
                className="flex-1 btn-danger font-bold"
              >
                Enable Live Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
