import React from 'react';

const statusConfig = {
  running: {
    color: 'bg-neon-green',
    glow: 'shadow-[0_0_10px_rgba(0,255,136,0.6)]',
    ringColor: 'pulse-dot-green',
    label: 'Running',
    textColor: 'text-neon-green',
  },
  paused: {
    color: 'bg-neon-yellow',
    glow: 'shadow-[0_0_10px_rgba(255,214,0,0.6)]',
    ringColor: 'pulse-dot-yellow',
    label: 'Paused',
    textColor: 'text-neon-yellow',
  },
  stopped: {
    color: 'bg-neon-red',
    glow: 'shadow-[0_0_10px_rgba(255,51,102,0.6)]',
    ringColor: '',
    label: 'Stopped',
    textColor: 'text-neon-red',
  },
  error: {
    color: 'bg-neon-red',
    glow: 'shadow-[0_0_10px_rgba(255,51,102,0.6)]',
    ringColor: 'pulse-dot-red',
    label: 'Error',
    textColor: 'text-neon-red',
    blink: true,
  },
};

export default function StatusBadge({ status = 'stopped' }) {
  const config = statusConfig[status?.toLowerCase()] || statusConfig.stopped;

  return (
    <div className="glass-pill px-4 py-1.5 flex items-center gap-2.5">
      <div className="relative">
        <div
          className={`w-2.5 h-2.5 rounded-full ${config.color} ${config.glow} ${
            config.blink ? 'animate-pulse' : ''
          }`}
        />
        {(status === 'running' || status === 'error') && (
          <div
            className={`absolute inset-0 w-2.5 h-2.5 rounded-full pulse-dot ${config.ringColor}`}
          />
        )}
      </div>
      <span
        className={`text-xs font-heading font-semibold uppercase tracking-wider ${config.textColor}`}
      >
        {config.label}
      </span>
    </div>
  );
}
