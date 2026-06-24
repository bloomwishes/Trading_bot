import { useState, useEffect, useCallback } from 'react';
import {
  Radar, Zap, TrendingUp, TrendingDown, RefreshCw, Brain, Shield,
  ArrowUpRight, ArrowDownRight, Minus, Search, Filter, ChevronDown,
  Activity, BarChart3, Eye, X,
} from 'lucide-react';
import { getLiveMarket, getAIAnalysis, manualTrade } from '../utils/api';
import { formatINR } from '../utils/formatters';

// ── Helpers ──────────────────────────────────────────────────────────────────

function getRecommendationStyle(rec) {
  const map = {
    'STRONG BUY':  { bg: 'bg-neon-green/20', border: 'border-neon-green/40', text: 'text-neon-green', icon: ArrowUpRight },
    'BUY':         { bg: 'bg-neon-green/10', border: 'border-neon-green/30', text: 'text-neon-green', icon: ArrowUpRight },
    'HOLD':        { bg: 'bg-neon-yellow/10', border: 'border-neon-yellow/30', text: 'text-neon-yellow', icon: Minus },
    'SELL':        { bg: 'bg-neon-red/10', border: 'border-neon-red/30', text: 'text-neon-red', icon: ArrowDownRight },
    'STRONG SELL': { bg: 'bg-neon-red/20', border: 'border-neon-red/40', text: 'text-neon-red', icon: ArrowDownRight },
  };
  return map[rec] || map['HOLD'];
}

function getRiskStyle(risk) {
  if (risk === 'Low') return 'text-neon-green';
  if (risk === 'Low-Medium') return 'text-neon-cyan';
  if (risk === 'Medium') return 'text-neon-yellow';
  if (risk === 'Medium-High') return 'text-orange-400';
  return 'text-neon-red';
}

function getChangeIcon(val) {
  if (val > 0) return <ArrowUpRight className="w-3.5 h-3.5" />;
  if (val < 0) return <ArrowDownRight className="w-3.5 h-3.5" />;
  return <Minus className="w-3.5 h-3.5" />;
}

function getChangeColor(val) {
  if (val > 0) return 'text-neon-green';
  if (val < 0) return 'text-neon-red';
  return 'text-gray-400';
}

function ScoreBar({ score }) {
  const color = score >= 70 ? 'bg-neon-green' : score >= 50 ? 'bg-neon-yellow' : score >= 30 ? 'bg-neon-cyan' : 'bg-gray-600';
  const glow = score >= 70 ? 'shadow-[0_0_6px_rgba(0,255,136,0.4)]' : '';
  return (
    <div className="flex items-center gap-2 w-full">
      <span className={`text-xs font-mono font-bold w-7 ${score >= 70 ? 'text-neon-green' : score >= 50 ? 'text-neon-yellow' : 'text-gray-400'}`}>
        {score}
      </span>
      <div className="flex-1 h-1.5 bg-cyber-surface rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color} ${glow}`} style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function Scanner() {
  const [coins, setCoins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [source, setSource] = useState('');
  const [totalPairs, setTotalPairs] = useState(0);

  // AI Analysis
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSource, setAiSource] = useState('');

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterRec, setFilterRec] = useState('ALL');
  const [sortBy, setSortBy] = useState('score');
  const [sortDir, setSortDir] = useState('desc');
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'grid'

  // Manual Trade States
  const [showTradeModal, setShowTradeModal] = useState(false);
  const [selectedCoin, setSelectedCoin] = useState(null);
  const [tradeSide, setTradeSide] = useState('BUY');
  const [tradeAmount, setTradeAmount] = useState('1000');
  const [tradeQty, setTradeQty] = useState('');
  const [useQty, setUseQty] = useState(false);
  const [tradeSL, setTradeSL] = useState('1.5');
  const [tradeTP, setTradeTP] = useState('3.0');
  const [executing, setExecuting] = useState(false);
  const [tradeError, setTradeError] = useState(null);
  const [tradeSuccess, setTradeSuccess] = useState(null);

  const handleOpenTradeModal = (coin, side) => {
    setSelectedCoin(coin);
    setTradeSide(side);
    setTradeAmount('1000');
    setTradeQty((1000 / coin.price).toFixed(6));
    setUseQty(false);
    setTradeSL('1.5');
    setTradeTP('3.0');
    setTradeError(null);
    setTradeSuccess(null);
    setShowTradeModal(true);
  };

  const handleAmountChange = (val) => {
    setTradeAmount(val);
    if (selectedCoin?.price) {
      setTradeQty((parseFloat(val || 0) / selectedCoin.price).toFixed(6));
    }
  };

  const handleQtyChange = (val) => {
    setTradeQty(val);
    if (selectedCoin?.price) {
      setTradeAmount((parseFloat(val || 0) * selectedCoin.price).toFixed(2));
    }
  };

  const handleSubmitTrade = async () => {
    setExecuting(true);
    setTradeError(null);
    setTradeSuccess(null);
    try {
      const payload = {
        pair: selectedCoin.pair,
        side: tradeSide,
        strategy: 'manual',
      };

      if (useQty) {
        payload.quantity = parseFloat(tradeQty);
      } else {
        payload.amount_inr = parseFloat(tradeAmount);
      }

      if (tradeSL) {
        payload.stop_loss = tradeSide === 'BUY'
          ? selectedCoin.price * (1 - parseFloat(tradeSL) / 100)
          : selectedCoin.price * (1 + parseFloat(tradeSL) / 100);
      }
      if (tradeTP) {
        payload.take_profit = tradeSide === 'BUY'
          ? selectedCoin.price * (1 + parseFloat(tradeTP) / 100)
          : selectedCoin.price * (1 - parseFloat(tradeTP) / 100);
      }

      await manualTrade(payload);
      setTradeSuccess(`Successfully executed manual ${tradeSide} trade for ${selectedCoin.symbol}!`);
      setTimeout(() => {
        setShowTradeModal(false);
      }, 2000);
    } catch (err) {
      setTradeError(err?.response?.data?.detail || 'Failed to execute manual trade');
    } finally {
      setExecuting(false);
    }
  };

  // ── Data fetch ─────────────────────────────────────────────────────────

  const fetchMarket = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const res = await getLiveMarket();
      const data = res.data;
      setCoins(data.coins || []);
      setSource(data.source || '');
      setTotalPairs(data.total_pairs || 0);
      setLastUpdate(new Date());
    } catch (err) {
      console.error('Market fetch failed:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchAIAnalysis = useCallback(async () => {
    setAiLoading(true);
    try {
      const topSymbols = coins
        .sort((a, b) => (b.volume || 0) - (a.volume || 0))
        .slice(0, 8)
        .map(c => c.symbol)
        .join(',');
      const res = await getAIAnalysis(topSymbols || 'BTC,ETH,SOL,XRP,DOGE');
      setAiAnalysis(res.data.analysis || '');
      setAiSource(res.data.ai_source || '');
    } catch (err) {
      console.error('AI analysis failed:', err);
      setAiAnalysis('AI analysis unavailable. Ensure Ollama is running with llama3 or mistral model.');
      setAiSource('error');
    } finally {
      setAiLoading(false);
    }
  }, [coins]);

  useEffect(() => {
    fetchMarket();
    const interval = setInterval(() => fetchMarket(false), 30000); // Auto-refresh every 30s
    return () => clearInterval(interval);
  }, [fetchMarket]);

  // ── Filtering & sorting ────────────────────────────────────────────────

  const filtered = coins
    .filter(c => {
      if (searchQuery && !c.symbol?.toLowerCase().includes(searchQuery.toLowerCase()) &&
          !c.pair?.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      if (filterRec !== 'ALL' && c.recommendation !== filterRec) return false;
      return true;
    })
    .sort((a, b) => {
      let aVal, bVal;
      switch (sortBy) {
        case 'score': aVal = a.score || 0; bVal = b.score || 0; break;
        case 'price': aVal = a.price || 0; bVal = b.price || 0; break;
        case 'change': aVal = a.change_24h || 0; bVal = b.change_24h || 0; break;
        case 'volume': aVal = a.volume || 0; bVal = b.volume || 0; break;
        case 'symbol': return sortDir === 'asc' ? (a.symbol || '').localeCompare(b.symbol || '') : (b.symbol || '').localeCompare(a.symbol || '');
        default: aVal = a.score || 0; bVal = b.score || 0;
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });

  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(col);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ col }) => {
    if (sortBy !== col) return <ChevronDown className="w-3 h-3 opacity-20" />;
    return <ChevronDown className={`w-3 h-3 text-neon-cyan transition-transform ${sortDir === 'asc' ? 'rotate-180' : ''}`} />;
  };

  // ── Stats ──────────────────────────────────────────────────────────────

  const buyCount = coins.filter(c => c.recommendation?.includes('BUY')).length;
  const sellCount = coins.filter(c => c.recommendation?.includes('SELL')).length;
  const holdCount = coins.filter(c => c.recommendation === 'HOLD').length;
  const avgChange = coins.length > 0
    ? (coins.reduce((s, c) => s + (c.change_24h || 0), 0) / coins.length).toFixed(2)
    : '0.00';

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold font-heading text-white">
            Live Market <span className="text-neon-cyan">Scanner</span>
          </h1>
          <p className="text-gray-400 mt-1">
            Real-time crypto prices, signals & AI analysis
            {lastUpdate && (
              <span className="ml-2 text-gray-600">
                • Updated: {lastUpdate.toLocaleTimeString()}
              </span>
            )}
            {source && (
              <span className="ml-2 text-gray-600">
                • Source: {source}
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={fetchAIAnalysis}
            disabled={aiLoading || coins.length === 0}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-neon-magenta/10 border border-neon-magenta/30
                       text-neon-magenta hover:bg-neon-magenta/20 transition-all duration-300
                       hover:shadow-[0_0_20px_rgba(255,0,229,0.15)] disabled:opacity-50 font-medium text-sm"
          >
            <Brain size={16} className={aiLoading ? 'animate-pulse' : ''} />
            {aiLoading ? 'Analyzing...' : 'AI Analysis'}
          </button>
          <button
            onClick={() => fetchMarket(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-neon-cyan/10 border border-neon-cyan/30
                       text-neon-cyan hover:bg-neon-cyan/20 transition-all duration-300
                       hover:shadow-[0_0_20px_rgba(0,240,255,0.15)] disabled:opacity-50 font-medium text-sm"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="glass-card p-4 text-center">
          <p className="text-[10px] uppercase text-gray-500 tracking-wider font-heading">Total Pairs</p>
          <p className="text-2xl font-bold font-mono text-white mt-1">{totalPairs}</p>
        </div>
        <div className="glass-card p-4 text-center">
          <p className="text-[10px] uppercase text-gray-500 tracking-wider font-heading">Buy Signals</p>
          <p className="text-2xl font-bold font-mono text-neon-green mt-1">{buyCount}</p>
        </div>
        <div className="glass-card p-4 text-center">
          <p className="text-[10px] uppercase text-gray-500 tracking-wider font-heading">Sell Signals</p>
          <p className="text-2xl font-bold font-mono text-neon-red mt-1">{sellCount}</p>
        </div>
        <div className="glass-card p-4 text-center">
          <p className="text-[10px] uppercase text-gray-500 tracking-wider font-heading">Avg 24h Change</p>
          <p className={`text-2xl font-bold font-mono mt-1 ${getChangeColor(parseFloat(avgChange))}`}>
            {avgChange > 0 ? '+' : ''}{avgChange}%
          </p>
        </div>
      </div>

      {/* AI Analysis Panel */}
      {aiAnalysis && (
        <div className="glass-card p-5 border border-neon-magenta/20 animate-slide-in">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-heading font-semibold text-white uppercase tracking-wider flex items-center gap-2">
              <Brain size={16} className="text-neon-magenta" />
              AI Market Analysis
            </h3>
            <span className="text-[10px] text-gray-500 bg-cyber-surface px-2 py-0.5 rounded-full">
              {aiSource}
            </span>
          </div>
          <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap font-mono bg-black/30 rounded-lg p-4 max-h-80 overflow-y-auto scrollbar-thin">
            {aiAnalysis}
          </div>
        </div>
      )}

      {/* Filters Bar */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Search coins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-cyber-surface/50 border border-gray-800
                         text-white text-sm placeholder-gray-600 focus:border-neon-cyan/40
                         focus:outline-none focus:ring-1 focus:ring-neon-cyan/20 transition-all"
            />
          </div>

          {/* Recommendation Filter */}
          <div className="flex items-center gap-1.5">
            <Filter size={14} className="text-gray-500" />
            {['ALL', 'STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL'].map((rec) => (
              <button
                key={rec}
                onClick={() => setFilterRec(rec)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                  filterRec === rec
                    ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30'
                    : 'bg-cyber-surface/30 text-gray-500 border border-transparent hover:text-gray-300'
                }`}
              >
                {rec}
              </button>
            ))}
          </div>

          {/* View toggle */}
          <div className="flex border border-gray-800 rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('table')}
              className={`px-3 py-1.5 text-xs ${viewMode === 'table' ? 'bg-neon-cyan/20 text-neon-cyan' : 'text-gray-500 hover:text-gray-300'}`}
            >
              <BarChart3 size={14} />
            </button>
            <button
              onClick={() => setViewMode('grid')}
              className={`px-3 py-1.5 text-xs ${viewMode === 'grid' ? 'bg-neon-cyan/20 text-neon-cyan' : 'text-gray-500 hover:text-gray-300'}`}
            >
              <Eye size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Market Data */}
      {loading ? (
        <div className="glass-card p-6 space-y-3">
          {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
            <div key={i} className="h-14 bg-cyber-surface/50 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Radar size={48} className="mx-auto mb-4 text-gray-600" />
          <p className="text-gray-400 text-lg">No coins match your filters</p>
          <p className="text-gray-600 text-sm mt-1">Try adjusting your search or filter criteria</p>
        </div>
      ) : viewMode === 'table' ? (
        /* ── Table View ───────────────────────────────────────────────── */
        <div className="glass-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800/50">
                  <th className="text-left p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => handleSort('symbol')}>
                    <span className="flex items-center gap-1">Coin <SortIcon col="symbol" /></span>
                  </th>
                  <th className="text-right p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => handleSort('price')}>
                    <span className="flex items-center justify-end gap-1">Price (₹) <SortIcon col="price" /></span>
                  </th>
                  <th className="text-right p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => handleSort('change')}>
                    <span className="flex items-center justify-end gap-1">24h Change <SortIcon col="change" /></span>
                  </th>
                  <th className="text-right p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => handleSort('volume')}>
                    <span className="flex items-center justify-end gap-1">Volume <SortIcon col="volume" /></span>
                  </th>
                  <th className="text-center p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    24h Range
                  </th>
                  <th className="text-center p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none" onClick={() => handleSort('score')}>
                    <span className="flex items-center justify-center gap-1">Signal Score <SortIcon col="score" /></span>
                  </th>
                  <th className="text-center p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    Action
                  </th>
                  <th className="text-center p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    Risk
                  </th>
                  <th className="text-center p-4 text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                    Execute
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/30">
                {filtered.map((coin, idx) => {
                  const recStyle = getRecommendationStyle(coin.recommendation);
                  const RecIcon = recStyle.icon;
                  return (
                    <tr
                      key={coin.symbol || idx}
                      className="hover:bg-white/[0.02] transition-colors duration-150 animate-slide-in"
                      style={{ animationDelay: `${Math.min(idx * 20, 400)}ms` }}
                    >
                      {/* Coin */}
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-neon-cyan/10 border border-neon-cyan/20 flex items-center justify-center">
                            <span className="text-xs font-bold text-neon-cyan">
                              {(coin.symbol || '?').slice(0, 2)}
                            </span>
                          </div>
                          <div>
                            <p className="font-semibold text-white text-sm">{coin.symbol}</p>
                            <p className="text-[10px] text-gray-500">{coin.pair}</p>
                          </div>
                        </div>
                      </td>

                      {/* Price */}
                      <td className="p-4 text-right">
                        <span className="font-mono font-semibold text-white text-sm">
                          {coin.price >= 1 ? `₹${coin.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : `₹${coin.price}`}
                        </span>
                      </td>

                      {/* 24h Change */}
                      <td className="p-4 text-right">
                        <span className={`flex items-center justify-end gap-1 font-mono font-semibold text-sm ${getChangeColor(coin.change_24h)}`}>
                          {getChangeIcon(coin.change_24h)}
                          {coin.change_24h > 0 ? '+' : ''}{coin.change_24h?.toFixed(2)}%
                        </span>
                      </td>

                      {/* Volume */}
                      <td className="p-4 text-right">
                        <span className="font-mono text-gray-400 text-xs">
                          {coin.volume >= 1e7 ? `₹${(coin.volume / 1e7).toFixed(1)}Cr` :
                           coin.volume >= 1e5 ? `₹${(coin.volume / 1e5).toFixed(1)}L` :
                           `₹${coin.volume?.toLocaleString('en-IN')}`}
                        </span>
                      </td>

                      {/* 24h Range */}
                      <td className="p-4">
                        {coin.high_24h > 0 ? (
                          <div className="flex items-center gap-2 justify-center">
                            <span className="text-[10px] text-gray-500 font-mono">{coin.low_24h?.toLocaleString('en-IN')}</span>
                            <div className="w-16 h-1 bg-cyber-surface rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-neon-red via-neon-yellow to-neon-green rounded-full"
                                style={{
                                  width: coin.high_24h - coin.low_24h > 0
                                    ? `${((coin.price - coin.low_24h) / (coin.high_24h - coin.low_24h)) * 100}%`
                                    : '50%',
                                }}
                              />
                            </div>
                            <span className="text-[10px] text-gray-500 font-mono">{coin.high_24h?.toLocaleString('en-IN')}</span>
                          </div>
                        ) : (
                          <span className="text-gray-600 text-xs">—</span>
                        )}
                      </td>

                      {/* Score */}
                      <td className="p-4">
                        <div className="w-28 mx-auto">
                          <ScoreBar score={coin.score || 0} />
                        </div>
                      </td>

                      {/* Action */}
                      <td className="p-4 text-center">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${recStyle.bg} ${recStyle.border} ${recStyle.text}`}>
                          <RecIcon className="w-3 h-3" />
                          {coin.recommendation}
                        </span>
                      </td>

                      {/* Risk */}
                      <td className="p-4 text-center">
                        <span className={`text-xs font-medium ${getRiskStyle(coin.risk_level)}`}>
                          <Shield className="w-3 h-3 inline mr-1" />
                          {coin.risk_level}
                        </span>
                      </td>

                      {/* Execute */}
                      <td className="p-4 text-center">
                        <div className="flex justify-center gap-1.5">
                          <button
                            onClick={() => handleOpenTradeModal(coin, 'BUY')}
                            className="px-2.5 py-1 text-xs font-bold bg-neon-green/10 hover:bg-neon-green/25 text-neon-green border border-neon-green/30 hover:border-neon-green/60 rounded transition-all duration-200"
                          >
                            Buy
                          </button>
                          <button
                            onClick={() => handleOpenTradeModal(coin, 'SELL')}
                            className="px-2.5 py-1 text-xs font-bold bg-neon-red/10 hover:bg-neon-red/25 text-neon-red border border-neon-red/30 hover:border-neon-red/60 rounded transition-all duration-200"
                          >
                            Sell
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="px-4 py-3 border-t border-gray-800/30 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              Showing {filtered.length} of {coins.length} pairs • Auto-refreshes every 30s
            </span>
          </div>
        </div>
      ) : (
        /* ── Grid View ────────────────────────────────────────────────── */
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          {filtered.map((coin, idx) => {
            const recStyle = getRecommendationStyle(coin.recommendation);
            return (
              <div
                key={coin.symbol || idx}
                className={`glass-card p-4 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg cursor-pointer border ${recStyle.border} animate-slide-in`}
                style={{ animationDelay: `${Math.min(idx * 30, 500)}ms` }}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-white text-sm">{coin.symbol}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${recStyle.bg} ${recStyle.text}`}>
                    {coin.recommendation}
                  </span>
                </div>
                <p className="font-mono font-bold text-white text-lg">
                  ₹{coin.price >= 1 ? coin.price.toLocaleString('en-IN') : coin.price}
                </p>
                <p className={`flex items-center gap-1 text-xs font-mono font-semibold mt-1 ${getChangeColor(coin.change_24h)}`}>
                  {getChangeIcon(coin.change_24h)}
                  {coin.change_24h > 0 ? '+' : ''}{coin.change_24h?.toFixed(2)}%
                </p>
                <div className="mt-3">
                  <ScoreBar score={coin.score || 0} />
                </div>
                <div className="flex gap-2 mt-4 pt-3 border-t border-gray-800/50">
                  <button
                    onClick={() => handleOpenTradeModal(coin, 'BUY')}
                    className="flex-1 py-1 text-center text-xs font-bold bg-neon-green/10 hover:bg-neon-green/20 text-neon-green border border-neon-green/30 rounded transition-all duration-200"
                  >
                    Buy
                  </button>
                  <button
                    onClick={() => handleOpenTradeModal(coin, 'SELL')}
                    className="flex-1 py-1 text-center text-xs font-bold bg-neon-red/10 hover:bg-neon-red/20 text-neon-red border border-neon-red/30 rounded transition-all duration-200"
                  >
                    Sell
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Manual Trade Modal */}
      {showTradeModal && selectedCoin && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="glass-card max-w-md w-full border-neon-cyan/40 shadow-[0_0_50px_rgba(0,240,255,0.15)] p-6 space-y-6 relative">
            
            {/* Close button */}
            <button
              onClick={() => setShowTradeModal(false)}
              className="absolute top-4 right-4 text-gray-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>

            {/* Header */}
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${
                tradeSide === 'BUY' 
                  ? 'bg-neon-green/10 border-neon-green/30 text-neon-green' 
                  : 'bg-neon-red/10 border-neon-red/30 text-neon-red'
              }`}>
                <Zap size={20} />
              </div>
              <div>
                <h3 className="text-xl font-heading font-bold text-white flex items-center gap-2">
                  Manual <span className={tradeSide === 'BUY' ? 'text-neon-green' : 'text-neon-red'}>{tradeSide}</span>
                </h3>
                <p className="text-xs text-gray-400 font-mono mt-0.5">
                  {selectedCoin.symbol} • Last: ₹{selectedCoin.price.toLocaleString('en-IN')}
                </p>
              </div>
            </div>

            {/* Error & Success Messages */}
            {tradeError && (
              <div className="bg-neon-red/10 border border-neon-red/30 rounded-lg p-3 text-xs text-neon-red font-medium">
                {tradeError}
              </div>
            )}
            {tradeSuccess && (
              <div className="bg-neon-green/10 border border-neon-green/30 rounded-lg p-3 text-xs text-neon-green font-medium">
                {tradeSuccess}
              </div>
            )}

            {/* Form Fields */}
            <div className="space-y-4">
              {/* Toggle Quantity / Amount */}
              <div className="flex justify-between items-center bg-cyber-surface/50 p-1 rounded-lg border border-gray-800">
                <button
                  type="button"
                  onClick={() => setUseQty(false)}
                  className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all ${
                    !useQty 
                      ? 'bg-cyber-surface text-neon-cyan shadow-[0_0_10px_rgba(0,240,255,0.15)] border border-neon-cyan/20' 
                      : 'text-gray-500 hover:text-gray-300 border border-transparent'
                  }`}
                >
                  Amount (INR)
                </button>
                <button
                  type="button"
                  onClick={() => setUseQty(true)}
                  className={`flex-1 py-1.5 rounded-md text-xs font-semibold transition-all ${
                    useQty 
                      ? 'bg-cyber-surface text-neon-cyan shadow-[0_0_10px_rgba(0,240,255,0.15)] border border-neon-cyan/20' 
                      : 'text-gray-500 hover:text-gray-300 border border-transparent'
                  }`}
                >
                  Quantity ({selectedCoin.symbol.replace('/INR', '').replace('-INR', '')})
                </button>
              </div>

              {/* Input Value */}
              {!useQty ? (
                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Amount in INR</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm font-mono">₹</span>
                    <input
                      type="number"
                      value={tradeAmount}
                      onChange={(e) => handleAmountChange(e.target.value)}
                      className="w-full pl-8 pr-4 py-2 bg-cyber-surface border border-gray-800 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-neon-cyan/40"
                      placeholder="Enter amount..."
                    />
                  </div>
                  <p className="text-[10px] text-gray-500 font-mono text-right">
                    Equivalent Qty: <span className="text-white font-bold">{tradeQty}</span>
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 tracking-wider">Quantity</label>
                  <input
                    type="number"
                    value={tradeQty}
                    onChange={(e) => handleQtyChange(e.target.value)}
                    className="w-full px-4 py-2 bg-cyber-surface border border-gray-800 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-neon-cyan/40"
                    placeholder="Enter quantity..."
                  />
                  <p className="text-[10px] text-gray-500 font-mono text-right">
                    Equivalent Cost: <span className="text-white font-bold">₹{parseFloat(tradeAmount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </p>
                </div>
              )}

              {/* Risk Settings (SL / TP) */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 tracking-wider flex items-center gap-1">
                    Stop Loss (%)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.1"
                      value={tradeSL}
                      onChange={(e) => setTradeSL(e.target.value)}
                      className="w-full px-4 py-2 bg-cyber-surface border border-gray-800 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-neon-cyan/40"
                      placeholder="1.5"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs font-mono">%</span>
                  </div>
                  {selectedCoin.price && tradeSL && (
                    <div className="text-[9px] text-gray-500 font-mono space-y-0.5 mt-1">
                      <p>Target: <span className="text-neon-red font-semibold">₹{(parseFloat(tradeAmount || 0) * (1 - parseFloat(tradeSL) / 100)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></p>
                      <p>SL Price: ₹{(tradeSide === 'BUY' 
                        ? selectedCoin.price * (1 - parseFloat(tradeSL) / 100) 
                        : selectedCoin.price * (1 + parseFloat(tradeSL) / 100)
                      ).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</p>
                    </div>
                  )}
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 tracking-wider flex items-center gap-1">
                    Take Profit (%)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.1"
                      value={tradeTP}
                      onChange={(e) => setTradeTP(e.target.value)}
                      className="w-full px-4 py-2 bg-cyber-surface border border-gray-800 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-neon-cyan/40"
                      placeholder="3.0"
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs font-mono">%</span>
                  </div>
                  {selectedCoin.price && tradeTP && (
                    <div className="text-[9px] text-gray-500 font-mono space-y-0.5 mt-1">
                      <p>Target: <span className="text-neon-green font-semibold">₹{(parseFloat(tradeAmount || 0) * (1 + parseFloat(tradeTP) / 100)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></p>
                      <p>TP Price: ₹{(tradeSide === 'BUY' 
                        ? selectedCoin.price * (1 + parseFloat(tradeTP) / 100) 
                        : selectedCoin.price * (1 - parseFloat(tradeTP) / 100)
                      ).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Buttons */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowTradeModal(false)}
                disabled={executing}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-cyber-surface border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 transition-all"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitTrade}
                disabled={executing || !tradeAmount || parseFloat(tradeAmount) <= 0}
                className={`px-5 py-2 rounded-lg text-sm font-bold text-white transition-all flex items-center gap-1.5 shadow-md disabled:opacity-50 disabled:cursor-not-allowed ${
                  tradeSide === 'BUY'
                    ? 'bg-neon-green hover:bg-green-600 shadow-[0_0_15px_rgba(0,255,136,0.3)]'
                    : 'bg-neon-red hover:bg-red-600 shadow-[0_0_15px_rgba(255,51,102,0.3)]'
                }`}
              >
                {executing ? 'Executing...' : `Execute ${tradeSide}`}
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
