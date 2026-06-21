import React, { useState, useEffect, useRef, useMemo } from 'react';
import { formatTime } from '../utils/formatters';

const levelConfig = {
  INFO: { color: 'text-neon-cyan', bg: 'bg-neon-cyan/5', badge: 'bg-neon-cyan/20 text-neon-cyan' },
  WARNING: { color: 'text-neon-yellow', bg: 'bg-neon-yellow/5', badge: 'bg-neon-yellow/20 text-neon-yellow' },
  WARN: { color: 'text-neon-yellow', bg: 'bg-neon-yellow/5', badge: 'bg-neon-yellow/20 text-neon-yellow' },
  ERROR: { color: 'text-neon-red', bg: 'bg-neon-red/5', badge: 'bg-neon-red/20 text-neon-red' },
  DEBUG: { color: 'text-gray-500', bg: 'bg-transparent', badge: 'bg-gray-500/20 text-gray-500' },
};

/**
 * Real-time log viewer with terminal aesthetics
 */
export default function LogViewer({
  messages = [],
  maxLines = 500,
  showFilters = true,
  className = '',
}) {
  const [activeFilter, setActiveFilter] = useState('ALL');
  const containerRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages, autoScroll]);

  // Handle manual scroll
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  };

  // Filter messages
  const filteredMessages = useMemo(() => {
    const recent = messages.slice(-maxLines);
    if (activeFilter === 'ALL') return recent;
    return recent.filter((msg) => {
      const level = (msg.level || msg.levelname || 'INFO').toUpperCase();
      return level === activeFilter;
    });
  }, [messages, activeFilter, maxLines]);

  const filters = ['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG'];

  return (
    <div className={`glass-card flex flex-col ${className}`}>
      {/* Filter bar */}
      {showFilters && (
        <div className="flex items-center gap-2 px-4 py-3 border-b border-neon-cyan/10">
          {filters.map((filter) => {
            const isActive = activeFilter === filter;
            const config = levelConfig[filter];
            return (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={`px-3 py-1 rounded text-xs font-heading font-semibold uppercase tracking-wider transition-all ${
                  isActive
                    ? filter === 'ALL'
                      ? 'bg-neon-cyan/20 text-neon-cyan'
                      : config?.badge || 'bg-neon-cyan/20 text-neon-cyan'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                }`}
              >
                {filter}
              </button>
            );
          })}

          <div className="flex-1" />

          {/* Auto-scroll indicator */}
          <div className="flex items-center gap-2">
            <div
              className={`w-1.5 h-1.5 rounded-full transition-colors ${
                autoScroll ? 'bg-neon-green shadow-[0_0_6px_rgba(0,255,136,0.6)]' : 'bg-gray-600'
              }`}
            />
            <span className="text-[10px] text-gray-500 uppercase tracking-wider font-heading">
              {autoScroll ? 'Auto-scroll' : 'Scrolled'}
            </span>
          </div>
        </div>
      )}

      {/* Log content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-6 min-h-[300px] max-h-[600px]"
        style={{
          background: 'rgba(5, 5, 10, 0.5)',
        }}
      >
        {filteredMessages.length === 0 ? (
          <div className="text-gray-600 text-center py-12">
            <p className="text-sm">No log entries</p>
            <p className="text-xs mt-1">Logs will appear here in real-time</p>
          </div>
        ) : (
          filteredMessages.map((msg, index) => {
            const level = (msg.level || msg.levelname || 'INFO').toUpperCase();
            const config = levelConfig[level] || levelConfig.INFO;
            const timestamp = msg.timestamp || msg.time || msg.created;
            const message = msg.message || msg.msg || (typeof msg === 'string' ? msg : JSON.stringify(msg));

            return (
              <div
                key={index}
                className={`flex gap-3 py-0.5 px-2 rounded hover:bg-white/[0.02] ${config.bg}`}
              >
                {/* Timestamp */}
                <span className="text-gray-600 shrink-0 w-[85px]">
                  {timestamp ? formatTime(timestamp) : '—'}
                </span>

                {/* Level badge */}
                <span
                  className={`shrink-0 w-[60px] text-center rounded px-1 ${config.badge}`}
                  style={{ fontSize: '10px' }}
                >
                  {level}
                </span>

                {/* Message */}
                <span className={`${config.color} break-all`}>{message}</span>
              </div>
            );
          })
        )}
      </div>

      {/* Status bar */}
      <div className="px-4 py-2 border-t border-neon-cyan/10 flex items-center justify-between">
        <span className="text-[10px] text-gray-600 font-mono">
          {filteredMessages.length} entries
          {activeFilter !== 'ALL' && ` (filtered: ${activeFilter})`}
        </span>
        <span className="text-[10px] text-gray-600 font-mono">
          Max: {maxLines} lines
        </span>
      </div>
    </div>
  );
}
