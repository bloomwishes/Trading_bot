import React, { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, X, Loader2 } from 'lucide-react';
import { formatINR, formatPair, formatPercent, getChangeColor, formatDuration } from '../utils/formatters';

/**
 * Skeleton loading row
 */
function SkeletonRow({ cols }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 shimmer rounded w-full" />
        </td>
      ))}
    </tr>
  );
}

/**
 * Reusable trade table component with sorting and optional actions
 */
export default function TradeTable({
  trades = [],
  loading = false,
  showActions = false,
  onClose,
  closingId,
  type = 'open', // 'open' or 'closed'
  emptyMessage = 'No trades found',
  emptyIcon: EmptyIcon = null,
}) {
  const [sortField, setSortField] = useState(null);
  const [sortDir, setSortDir] = useState('desc');

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sortedTrades = useMemo(() => {
    if (!sortField || !trades.length) return trades;
    return [...trades].sort((a, b) => {
      let aVal = a[sortField];
      let bVal = b[sortField];
      if (typeof aVal === 'string') aVal = aVal.toLowerCase();
      if (typeof bVal === 'string') bVal = bVal.toLowerCase();
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [trades, sortField, sortDir]);

  const SortHeader = ({ field, label }) => (
    <th
      className="cursor-pointer hover:text-neon-cyan transition-colors select-none"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1">
        {label}
        {sortField === field && (
          sortDir === 'asc' ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )
        )}
      </div>
    </th>
  );

  const columns = type === 'open'
    ? ['pair', 'strategy', 'side', 'entry_price', 'current_price', 'quantity', 'pnl', 'pnl_pct', 'stop_loss', 'take_profit', 'duration']
    : ['pair', 'strategy', 'side', 'entry_price', 'exit_price', 'quantity', 'pnl', 'pnl_pct', 'status'];

  if (loading) {
    return (
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="cyber-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col}>{col.replace(/_/g, ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, i) => (
                <SkeletonRow key={i} cols={columns.length} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (!trades.length) {
    return (
      <div className="glass-card p-12 text-center">
        {EmptyIcon && <EmptyIcon className="w-16 h-16 text-gray-600 mx-auto mb-4" />}
        <p className="text-gray-500 text-lg font-heading">{emptyMessage}</p>
        <p className="text-gray-600 text-sm mt-2">Trades will appear here when positions are opened</p>
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="cyber-table">
          <thead>
            <tr>
              <SortHeader field="pair" label="Pair" />
              <SortHeader field="strategy" label="Strategy" />
              <SortHeader field="side" label="Side" />
              <SortHeader field="entry_price" label="Entry Price" />
              {type === 'open' ? (
                <SortHeader field="current_price" label="Current Price" />
              ) : (
                <SortHeader field="exit_price" label="Exit Price" />
              )}
              <SortHeader field="quantity" label="Qty" />
              <SortHeader field="pnl" label="P&L" />
              <th>P&L %</th>
              {type === 'open' && (
                <>
                  <th>SL</th>
                  <th>TP</th>
                  <th>Duration</th>
                </>
              )}
              {type === 'closed' && <SortHeader field="status" label="Status" />}
              {showActions && <th>Action</th>}
            </tr>
          </thead>
          <tbody>
            {sortedTrades.map((trade, index) => {
              const pnl = trade.pnl || trade.unrealized_pnl || 0;
              const pnlPct = trade.pnl_pct || trade.pnl_percent || 0;
              const { text: pctText, colorClass: pctColor } = formatPercent(pnlPct);

              return (
                <tr key={trade.id || index} className="animate-fade-in" style={{ animationDelay: `${index * 30}ms` }}>
                  <td>
                    <span className="font-mono font-semibold text-white">
                      {formatPair(trade.pair || trade.symbol)}
                    </span>
                  </td>
                  <td>
                    <span className="px-2 py-0.5 rounded text-xs bg-neon-cyan/10 text-neon-cyan/80 font-heading">
                      {trade.strategy || '—'}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                        trade.side?.toLowerCase() === 'buy'
                          ? 'bg-neon-green/10 text-neon-green'
                          : 'bg-neon-red/10 text-neon-red'
                      }`}
                    >
                      {trade.side || '—'}
                    </span>
                  </td>
                  <td className="font-mono text-gray-300">{formatINR(trade.entry_price)}</td>
                  <td className="font-mono text-gray-300">
                    {formatINR(type === 'open' ? trade.current_price : trade.exit_price)}
                  </td>
                  <td className="font-mono text-gray-400">{trade.quantity || '—'}</td>
                  <td className={`font-mono font-semibold ${getChangeColor(pnl)}`}>
                    {pnl >= 0 ? '+' : ''}
                    {formatINR(pnl)}
                  </td>
                  <td className={`font-mono font-semibold ${pctColor}`}>{pctText}</td>
                  {type === 'open' && (
                    <>
                      <td className="font-mono text-neon-red/60 text-xs">
                        {trade.stop_loss ? formatINR(trade.stop_loss) : '—'}
                      </td>
                      <td className="font-mono text-neon-green/60 text-xs">
                        {trade.take_profit ? formatINR(trade.take_profit) : '—'}
                      </td>
                      <td className="text-gray-400 text-xs">
                        {formatDuration(trade.opened_at || trade.entry_time)}
                      </td>
                    </>
                  )}
                  {type === 'closed' && (
                    <td>
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          trade.status === 'closed'
                            ? 'bg-gray-500/10 text-gray-400'
                            : trade.status === 'stopped'
                            ? 'bg-neon-red/10 text-neon-red'
                            : 'bg-neon-yellow/10 text-neon-yellow'
                        }`}
                      >
                        {trade.status || 'closed'}
                      </span>
                    </td>
                  )}
                  {showActions && (
                    <td>
                      <button
                        onClick={() => onClose?.(trade.id)}
                        disabled={closingId === trade.id}
                        className="btn-danger text-xs py-1 px-3 flex items-center gap-1"
                      >
                        {closingId === trade.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <X className="w-3 h-3" />
                        )}
                        Close
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
