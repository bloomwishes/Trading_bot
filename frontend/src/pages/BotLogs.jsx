import { useState, useRef, useEffect, useCallback } from 'react';
import { Terminal, Download, Trash2, Pause, Play } from 'lucide-react';
import useWebSocket from '../hooks/useWebSocket';

export default function BotLogs() {
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState('ALL');
  const [paused, setPaused] = useState(false);
  const logContainerRef = useRef(null);
  const maxLogs = 500;

  const { data: wsData, isConnected } = useWebSocket('ws://localhost:8000/ws/logs');

  useEffect(() => {
    if (wsData && !paused) {
      setLogs(prev => {
        const updated = [...prev, { ...wsData, id: Date.now() + Math.random() }];
        return updated.slice(-maxLogs);
      });
    }
  }, [wsData, paused]);

  // Auto-scroll
  useEffect(() => {
    if (logContainerRef.current && !paused) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, paused]);

  const getLevelColor = (level) => {
    const colors = {
      INFO: 'text-neon-cyan',
      WARNING: 'text-neon-yellow',
      ERROR: 'text-neon-red',
      DEBUG: 'text-gray-500',
    };
    return colors[level] || 'text-gray-400';
  };

  const getLevelBg = (level) => {
    const colors = {
      INFO: 'bg-neon-cyan/5',
      WARNING: 'bg-neon-yellow/5',
      ERROR: 'bg-neon-red/5',
      DEBUG: 'bg-transparent',
    };
    return colors[level] || '';
  };

  const filteredLogs = filter === 'ALL' ? logs : logs.filter(l => l.level === filter);

  const clearLogs = () => setLogs([]);

  const downloadLogs = () => {
    const text = logs.map(l => `[${l.timestamp || new Date().toISOString()}] [${l.level}] ${l.message}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `autotrader_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const filterButtons = [
    { label: 'ALL', count: logs.length },
    { label: 'INFO', count: logs.filter(l => l.level === 'INFO').length },
    { label: 'WARNING', count: logs.filter(l => l.level === 'WARNING').length },
    { label: 'ERROR', count: logs.filter(l => l.level === 'ERROR').length },
  ];

  return (
    <div className="h-full flex flex-col space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold font-heading text-white">
            Bot <span className="text-neon-cyan">Logs</span>
          </h1>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-cyber-card border border-gray-800">
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-neon-green animate-pulse' : 'bg-neon-red'}`} />
            <span className="text-xs text-gray-400">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused(!paused)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-all
              ${paused
                ? 'bg-neon-yellow/10 border-neon-yellow/30 text-neon-yellow'
                : 'bg-cyber-card border-gray-700 text-gray-400 hover:border-gray-500'}`}
          >
            {paused ? <><Play size={14} /> Resume</> : <><Pause size={14} /> Pause</>}
          </button>
          <button
            onClick={clearLogs}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyber-card border border-gray-700 
                       text-gray-400 hover:border-neon-red/30 hover:text-neon-red text-sm transition-all"
          >
            <Trash2 size={14} />
            Clear
          </button>
          <button
            onClick={downloadLogs}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cyber-card border border-gray-700 
                       text-gray-400 hover:border-neon-cyan/30 hover:text-neon-cyan text-sm transition-all"
          >
            <Download size={14} />
            Download
          </button>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex gap-2">
        {filterButtons.map(btn => (
          <button
            key={btn.label}
            onClick={() => setFilter(btn.label)}
            className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all duration-300
              ${filter === btn.label
                ? btn.label === 'ERROR' 
                  ? 'bg-neon-red/15 border-neon-red/40 text-neon-red'
                  : btn.label === 'WARNING'
                    ? 'bg-neon-yellow/15 border-neon-yellow/40 text-neon-yellow'
                    : 'bg-neon-cyan/15 border-neon-cyan/40 text-neon-cyan'
                : 'bg-cyber-card border-gray-800 text-gray-500 hover:border-gray-600'}`}
          >
            {btn.label}
            <span className="ml-2 text-xs opacity-60">({btn.count})</span>
          </button>
        ))}
      </div>

      {/* Terminal Log Viewer */}
      <div className="flex-1 min-h-0">
        <div
          className="glass-card h-full min-h-[500px] overflow-hidden flex flex-col"
          style={{
            background: 'linear-gradient(180deg, rgba(10,10,15,0.95) 0%, rgba(10,10,15,0.98) 100%)',
            border: '1px solid rgba(0,240,255,0.08)',
          }}
        >
          {/* Terminal Header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-800/50 bg-cyber-bg/50">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-neon-red/60" />
              <div className="w-3 h-3 rounded-full bg-neon-yellow/60" />
              <div className="w-3 h-3 rounded-full bg-neon-green/60" />
            </div>
            <div className="flex-1 text-center">
              <span className="text-xs text-gray-600 font-mono">autotrader-pro — logs</span>
            </div>
            <Terminal size={14} className="text-gray-600" />
          </div>

          {/* Log Content */}
          <div
            ref={logContainerRef}
            className="flex-1 overflow-y-auto p-4 font-mono text-sm leading-6 custom-scrollbar"
          >
            {filteredLogs.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <Terminal size={32} className="mx-auto mb-3 text-gray-700" />
                  <p className="text-gray-600 text-sm">
                    {logs.length === 0 
                      ? 'Waiting for log entries...' 
                      : `No ${filter} logs to display`}
                  </p>
                  {!isConnected && (
                    <p className="text-neon-red/50 text-xs mt-2">
                      WebSocket disconnected — logs may not be streaming
                    </p>
                  )}
                </div>
              </div>
            ) : (
              filteredLogs.map((log, i) => (
                <div
                  key={log.id || i}
                  className={`flex gap-3 py-0.5 px-2 rounded hover:bg-white/[0.02] transition-colors ${getLevelBg(log.level)}`}
                >
                  <span className="text-gray-600 flex-shrink-0 text-xs leading-6">
                    {log.timestamp
                      ? new Date(log.timestamp).toLocaleTimeString('en-IN', { hour12: false })
                      : new Date().toLocaleTimeString('en-IN', { hour12: false })}
                  </span>
                  <span className={`flex-shrink-0 font-bold text-xs leading-6 w-16 ${getLevelColor(log.level)}`}>
                    [{log.level || 'INFO'}]
                  </span>
                  <span className="text-gray-300 break-all">
                    {log.message}
                  </span>
                </div>
              ))
            )}

            {/* Blinking cursor */}
            {!paused && (
              <div className="flex items-center gap-1 mt-1 text-neon-cyan/50">
                <span className="animate-pulse">▊</span>
              </div>
            )}
          </div>

          {/* Status Bar */}
          <div className="flex items-center justify-between px-4 py-1.5 border-t border-gray-800/50 bg-cyber-bg/50 text-xs text-gray-600">
            <span>{filteredLogs.length} log entries</span>
            <span>{paused ? '⏸ Paused' : '● Live'}</span>
            <span>Max: {maxLogs}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
