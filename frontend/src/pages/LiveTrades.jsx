import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, TrendingDown, X, AlertTriangle, RefreshCw } from 'lucide-react';
import { getOpenTrades, closeTrade } from '../utils/api';
import { formatINR, formatPercent, formatDate } from '../utils/formatters';
import TradeTable from '../components/TradeTable';

export default function LiveTrades() {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(null);
  const [showConfirm, setShowConfirm] = useState(null);
  const [error, setError] = useState(null);

  const fetchTrades = useCallback(async () => {
    try {
      const res = await getOpenTrades();
      setTrades(res.data || []);
      setError(null);
    } catch (err) {
      setError('Failed to fetch open trades');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(fetchTrades, 10000);
    return () => clearInterval(interval);
  }, [fetchTrades]);

  const handleClose = async (tradeId) => {
    setClosing(tradeId);
    try {
      await closeTrade(tradeId);
      setTrades(prev => prev.filter(t => t.id !== tradeId));
      setShowConfirm(null);
    } catch (err) {
      setError('Failed to close trade');
    } finally {
      setClosing(null);
    }
  };

  const getDuration = (createdAt) => {
    const ms = Date.now() - new Date(createdAt).getTime();
    const mins = Math.floor(ms / 60000);
    const hrs = Math.floor(mins / 60);
    if (hrs > 0) return `${hrs}h ${mins % 60}m`;
    return `${mins}m`;
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white">
            Live <span className="text-neon-cyan">Trades</span>
          </h1>
          <p className="text-gray-400 mt-1">Monitor your open positions in real-time</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">
            {trades.length} open position{trades.length !== 1 ? 's' : ''}
          </span>
          <button
            onClick={() => { setLoading(true); fetchTrades(); }}
            className="p-2 rounded-lg bg-cyber-card border border-neon-cyan/20 hover:border-neon-cyan/50 
                       text-neon-cyan transition-all duration-300 hover:shadow-[0_0_15px_rgba(0,240,255,0.2)]"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="glass-card border-neon-red/30 p-4 flex items-center gap-3">
          <AlertTriangle className="text-neon-red" size={20} />
          <span className="text-neon-red">{error}</span>
        </div>
      )}

      {/* Trades Table */}
      {loading ? (
        <div className="glass-card p-8">
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-cyber-surface/50 rounded-lg animate-pulse" />
            ))}
          </div>
        </div>
      ) : trades.length === 0 ? (
        <div className="glass-card p-16 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-cyber-surface flex items-center justify-center">
            <TrendingUp className="text-gray-600" size={36} />
          </div>
          <h3 className="text-xl font-heading text-gray-400 mb-2">No Open Trades</h3>
          <p className="text-gray-600">
            Your bot will open positions when strategies detect opportunities
          </p>
        </div>
      ) : (
        <div className="glass-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-neon-cyan/10">
                  <th className="text-left p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Pair</th>
                  <th className="text-left p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Strategy</th>
                  <th className="text-left p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Side</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Entry Price</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Current Price</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Quantity</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Unrealized P&L</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Stop Loss</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Take Profit</th>
                  <th className="text-right p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Duration</th>
                  <th className="text-center p-4 text-xs font-medium text-gray-400 uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cyber-surface/50">
                {trades.map((trade) => {
                  const pnl = trade.pnl || ((trade.current_price || trade.entry_price) - trade.entry_price) * trade.quantity * (trade.side === 'BUY' ? 1 : -1);
                  const pnlPct = trade.entry_price ? ((trade.current_price || trade.entry_price) - trade.entry_price) / trade.entry_price * 100 * (trade.side === 'BUY' ? 1 : -1) : 0;
                  const isProfit = pnl >= 0;

                  return (
                    <tr key={trade.id} className="hover:bg-cyber-surface/30 transition-colors duration-200">
                      <td className="p-4">
                        <span className="font-semibold text-white">{trade.pair}</span>
                      </td>
                      <td className="p-4">
                        <span className="px-2 py-1 rounded-md text-xs font-medium bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20">
                          {trade.strategy}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className={`flex items-center gap-1 font-semibold ${trade.side === 'BUY' ? 'text-neon-green' : 'text-neon-red'}`}>
                          {trade.side === 'BUY' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                          {trade.side}
                        </span>
                      </td>
                      <td className="p-4 text-right text-gray-300 font-mono text-sm">
                        {formatINR(trade.entry_price)}
                      </td>
                      <td className="p-4 text-right font-mono text-sm">
                        <span className={isProfit ? 'text-neon-green' : 'text-neon-red'}>
                          {formatINR(trade.current_price || trade.entry_price)}
                        </span>
                      </td>
                      <td className="p-4 text-right text-gray-300 font-mono text-sm">
                        {trade.quantity?.toFixed(6)}
                      </td>
                      <td className="p-4 text-right">
                        <div className={`font-semibold font-mono ${isProfit ? 'text-neon-green' : 'text-neon-red'}`}>
                          {isProfit ? '+' : ''}{formatINR(pnl)}
                        </div>
                        <div className={`text-xs ${isProfit ? 'text-neon-green/70' : 'text-neon-red/70'}`}>
                          {isProfit ? '+' : ''}{pnlPct.toFixed(2)}%
                        </div>
                      </td>
                      <td className="p-4 text-right text-neon-red/70 font-mono text-sm">
                        {trade.stop_loss ? formatINR(trade.stop_loss) : '—'}
                      </td>
                      <td className="p-4 text-right text-neon-green/70 font-mono text-sm">
                        {trade.take_profit ? formatINR(trade.take_profit) : '—'}
                      </td>
                      <td className="p-4 text-right text-gray-400 text-sm">
                        {getDuration(trade.created_at)}
                      </td>
                      <td className="p-4 text-center">
                        {showConfirm === trade.id ? (
                          <div className="flex items-center gap-2 justify-center">
                            <button
                              onClick={() => handleClose(trade.id)}
                              disabled={closing === trade.id}
                              className="px-3 py-1 rounded text-xs font-medium bg-neon-red/20 text-neon-red 
                                         border border-neon-red/30 hover:bg-neon-red/30 transition-all"
                            >
                              {closing === trade.id ? '...' : 'Yes'}
                            </button>
                            <button
                              onClick={() => setShowConfirm(null)}
                              className="px-3 py-1 rounded text-xs font-medium bg-cyber-surface text-gray-400 
                                         border border-gray-700 hover:border-gray-500 transition-all"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setShowConfirm(trade.id)}
                            className="p-2 rounded-lg bg-neon-red/10 text-neon-red border border-neon-red/20 
                                       hover:bg-neon-red/20 hover:border-neon-red/40 transition-all duration-300
                                       hover:shadow-[0_0_10px_rgba(255,51,102,0.2)]"
                            title="Close trade"
                          >
                            <X size={16} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Summary Bar */}
      {trades.length > 0 && (
        <div className="glass-card p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-xs text-gray-500 uppercase mb-1">Total Positions</div>
              <div className="text-lg font-bold text-white">{trades.length}</div>
            </div>
            <div className="text-center">
              <div className="text-xs text-gray-500 uppercase mb-1">Total Invested</div>
              <div className="text-lg font-bold text-neon-cyan font-mono">
                {formatINR(trades.reduce((sum, t) => sum + (t.entry_price * t.quantity), 0))}
              </div>
            </div>
            <div className="text-center">
              <div className="text-xs text-gray-500 uppercase mb-1">Unrealized P&L</div>
              {(() => {
                const totalPnl = trades.reduce((sum, t) => {
                  const cp = t.current_price || t.entry_price;
                  return sum + (cp - t.entry_price) * t.quantity * (t.side === 'BUY' ? 1 : -1);
                }, 0);
                return (
                  <div className={`text-lg font-bold font-mono ${totalPnl >= 0 ? 'text-neon-green' : 'text-neon-red'}`}>
                    {totalPnl >= 0 ? '+' : ''}{formatINR(totalPnl)}
                  </div>
                );
              })()}
            </div>
            <div className="text-center">
              <div className="text-xs text-gray-500 uppercase mb-1">Buy / Sell</div>
              <div className="text-lg font-bold">
                <span className="text-neon-green">{trades.filter(t => t.side === 'BUY').length}</span>
                <span className="text-gray-600 mx-1">/</span>
                <span className="text-neon-red">{trades.filter(t => t.side === 'SELL').length}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
