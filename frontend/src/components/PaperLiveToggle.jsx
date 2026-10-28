import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';

export default function PaperLiveToggle({ mode = 'paper', onToggle, disabled = false }) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const isPaper = mode === 'paper';

  // Handle ESC key to dismiss modal
  useEffect(() => {
    if (!showConfirm) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !isSubmitting) {
        closeModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showConfirm, isSubmitting]);

  const closeModal = () => {
    setShowConfirm(false);
    setErrorMsg(null);
    setSuccessMsg(null);
    setIsSubmitting(false);
  };

  const handleClick = () => {
    if (disabled || isSubmitting) return;
    if (isPaper) {
      // Switching to Live — show confirmation
      setErrorMsg(null);
      setSuccessMsg(null);
      setShowConfirm(true);
    } else {
      // Switching to Paper — no confirmation needed
      onToggle?.('paper');
    }
  };

  const confirmLive = async () => {
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await onToggle?.('live');
      setSuccessMsg('Live mode enabled successfully!');
      setTimeout(() => {
        closeModal();
      }, 700);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to switch to live mode.';
      setErrorMsg(detail);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      {/* Toggle */}
      <button
        onClick={handleClick}
        disabled={disabled || isSubmitting}
        className={`relative flex items-center gap-2 rounded-full px-1 py-1 transition-all duration-300 ${
          disabled || isSubmitting ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
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
            onClick={isSubmitting ? undefined : closeModal}
          />

          {/* Modal Card - centrally positioned in viewport */}
          <div className="relative glass-card p-6 sm:p-7 max-w-md w-full mx-auto my-auto rounded-2xl border border-neon-red/40 shadow-[0_0_50px_rgba(255,51,102,0.25)] animate-slide-in z-10 bg-cyber-card/95">
            {!isSubmitting && (
              <button
                onClick={closeModal}
                className="absolute top-4 right-4 p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/10 transition-colors"
                aria-label="Close dialog"
              >
                <X className="w-5 h-5" />
              </button>
            )}

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

            <div className="bg-neon-red/10 border border-neon-red/30 rounded-xl p-4 mb-4">
              <p className="text-sm text-gray-200 leading-relaxed">
                <span className="text-neon-red font-bold">⚠ Warning:</span> Live mode executes orders with{' '}
                <span className="text-neon-red font-bold underline">REAL money</span> on CoinDCX.
                Verify your API keys, balance, and risk thresholds before proceeding.
              </p>
            </div>

            {/* Error Message Alert */}
            {errorMsg && (
              <div className="bg-red-500/15 border border-red-500/50 rounded-xl p-3.5 mb-4 text-xs text-red-200 flex items-start gap-2.5 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                <span className="leading-relaxed font-sans">{errorMsg}</span>
              </div>
            )}

            {/* Success Message Alert */}
            {successMsg && (
              <div className="bg-green-500/15 border border-green-500/50 rounded-xl p-3.5 mb-4 text-xs text-green-200 flex items-start gap-2.5 shadow-[0_0_15px_rgba(34,197,94,0.2)]">
                <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                <span className="leading-relaxed font-sans">{successMsg}</span>
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={closeModal}
                className="flex-1 btn-neon py-2.5 font-medium disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={confirmLive}
                className="flex-1 btn-danger py-2.5 font-bold shadow-[0_0_20px_rgba(255,51,102,0.4)] flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Verifying...</span>
                  </>
                ) : (
                  <span>Enable Live Mode</span>
                )}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
