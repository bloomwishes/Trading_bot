import { useState, useEffect } from 'react';
import { Brain, Filter, ChevronDown, ChevronUp, CheckCircle, XCircle } from 'lucide-react';
import { getLLMDecisions } from '../utils/api';
import { formatDate } from '../utils/formatters';

export default function LLMDecisions() {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);
  const [filters, setFilters] = useState({
    pair: '',
    action: '',
    acted_on: '',
  });

  useEffect(() => {
    fetchDecisions();
  }, []);

  const fetchDecisions = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filters.pair) params.pair = filters.pair;
      if (filters.acted_on !== '') params.acted_on = filters.acted_on === 'true';
      const res = await getLLMDecisions(params);
      setDecisions(res.data || []);
    } catch (err) {
      console.error('Failed to fetch LLM decisions:', err);
    } finally {
      setLoading(false);
    }
  };

  const getActionBadge = (action) => {
    const styles = {
      BUY: 'bg-neon-green/15 text-neon-green border-neon-green/30',
      SELL: 'bg-neon-red/15 text-neon-red border-neon-red/30',
      HOLD: 'bg-neon-yellow/15 text-neon-yellow border-neon-yellow/30',
    };
    return styles[action] || 'bg-gray-800 text-gray-400 border-gray-700';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.75) return { bar: 'bg-neon-green', text: 'text-neon-green' };
    if (confidence >= 0.5) return { bar: 'bg-neon-yellow', text: 'text-neon-yellow' };
    return { bar: 'bg-neon-red', text: 'text-neon-red' };
  };

  const pairs = [...new Set(decisions.map(d => d.pair))];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold font-heading text-white">
          AI <span className="text-neon-cyan">Decisions</span>
        </h1>
        <p className="text-gray-400 mt-1">
          Ollama LLM analysis log — every decision the AI has made
        </p>
      </div>

      {/* Filters */}
      <div className="glass-card p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-400">
            <Filter size={16} />
            <span>Filter:</span>
          </div>
          <select
            value={filters.pair}
            onChange={e => setFilters(p => ({ ...p, pair: e.target.value }))}
            className="bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white
                       focus:border-neon-cyan/50 focus:outline-none transition-colors"
          >
            <option value="">All Pairs</option>
            {pairs.map(p => <option key={p} value={p}>{p}</option>)}
          </select>

          <div className="flex gap-2">
            {['', 'BUY', 'SELL', 'HOLD'].map(action => (
              <button
                key={action || 'all'}
                onClick={() => setFilters(p => ({ ...p, action }))}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all
                  ${filters.action === action
                    ? 'bg-neon-cyan/20 border-neon-cyan/40 text-neon-cyan'
                    : 'bg-cyber-surface border-gray-700 text-gray-500 hover:border-gray-500'}`}
              >
                {action || 'All'}
              </button>
            ))}
          </div>

          <select
            value={filters.acted_on}
            onChange={e => setFilters(p => ({ ...p, acted_on: e.target.value }))}
            className="bg-cyber-surface border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white
                       focus:border-neon-cyan/50 focus:outline-none transition-colors"
          >
            <option value="">Acted: All</option>
            <option value="true">Executed</option>
            <option value="false">Not Executed</option>
          </select>

          <button
            onClick={fetchDecisions}
            className="px-4 py-1.5 rounded-lg bg-neon-cyan/15 border border-neon-cyan/30 text-neon-cyan 
                       text-sm hover:bg-neon-cyan/25 transition-all"
          >
            Apply
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Decisions', value: decisions.length, color: 'neon-cyan' },
          { label: 'Executed', value: decisions.filter(d => d.acted_on).length, color: 'neon-green' },
          { label: 'Avg Confidence', value: decisions.length ? `${(decisions.reduce((s, d) => s + (d.confidence || 0), 0) / decisions.length * 100).toFixed(0)}%` : '—', color: 'neon-yellow' },
          { label: 'High Confidence', value: decisions.filter(d => (d.confidence || 0) >= 0.75).length, color: 'neon-magenta' },
        ].map((stat, i) => (
          <div key={i} className="glass-card p-4">
            <div className="text-xs text-gray-500 uppercase mb-1">{stat.label}</div>
            <div className={`text-2xl font-bold font-mono text-${stat.color}`}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Decisions Table */}
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-3">
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="h-16 bg-cyber-surface/50 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : decisions.length === 0 ? (
          <div className="p-16 text-center">
            <Brain size={48} className="mx-auto mb-4 text-gray-700" />
            <h3 className="text-lg font-heading text-gray-500 mb-2">No AI Decisions Yet</h3>
            <p className="text-gray-600 text-sm">
              The Sentiment LLM strategy will log its decisions here when enabled
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-neon-cyan/10">
                  <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                  <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase">Pair</th>
                  <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Action</th>
                  <th className="text-left p-4 text-xs font-medium text-gray-500 uppercase w-48">Confidence</th>
                  <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Executed</th>
                  <th className="text-center p-4 text-xs font-medium text-gray-500 uppercase">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cyber-surface/30">
                {decisions
                  .filter(d => !filters.action || d.action === filters.action)
                  .map((decision) => {
                    const confColor = getConfidenceColor(decision.confidence || 0);
                    const isExpanded = expandedRow === decision.id;

                    return (
                      <>
                        <tr
                          key={decision.id}
                          className="hover:bg-cyber-surface/20 transition-colors duration-200 cursor-pointer"
                          onClick={() => setExpandedRow(isExpanded ? null : decision.id)}
                        >
                          <td className="p-4 text-sm text-gray-400">
                            {formatDate(decision.created_at)}
                          </td>
                          <td className="p-4">
                            <span className="font-semibold text-white">{decision.pair}</span>
                          </td>
                          <td className="p-4 text-center">
                            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getActionBadge(decision.action)}`}>
                              {decision.action}
                            </span>
                          </td>
                          <td className="p-4">
                            <div className="flex items-center gap-3">
                              <div className="flex-1 h-2.5 bg-cyber-surface rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-500 ${confColor.bar}`}
                                  style={{ width: `${(decision.confidence || 0) * 100}%` }}
                                />
                              </div>
                              <span className={`text-sm font-bold font-mono ${confColor.text} min-w-[3rem] text-right`}>
                                {((decision.confidence || 0) * 100).toFixed(0)}%
                              </span>
                            </div>
                          </td>
                          <td className="p-4 text-center">
                            {decision.acted_on ? (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-neon-green/15 text-neon-green border border-neon-green/30">
                                <CheckCircle size={12} /> Yes
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-gray-800 text-gray-500 border border-gray-700">
                                <XCircle size={12} /> No
                              </span>
                            )}
                          </td>
                          <td className="p-4 text-center">
                            {isExpanded ? (
                              <ChevronUp size={18} className="mx-auto text-neon-cyan" />
                            ) : (
                              <ChevronDown size={18} className="mx-auto text-gray-500" />
                            )}
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr key={`${decision.id}-detail`}>
                            <td colSpan="6" className="p-0">
                              <div className="px-6 py-4 bg-cyber-surface/30 border-l-2 border-neon-cyan/30 animate-slide-in">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  <div>
                                    <h4 className="text-xs text-gray-500 uppercase mb-2 flex items-center gap-1">
                                      <Brain size={12} /> AI Reasoning
                                    </h4>
                                    <p className="text-sm text-gray-300 leading-relaxed bg-cyber-bg/50 rounded-lg p-3">
                                      {decision.reason || 'No reasoning provided'}
                                    </p>
                                  </div>
                                  <div>
                                    <h4 className="text-xs text-gray-500 uppercase mb-2">Full Response</h4>
                                    <pre className="text-xs text-gray-500 bg-cyber-bg/50 rounded-lg p-3 overflow-x-auto max-h-32 font-mono">
                                      {decision.response || '—'}
                                    </pre>
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
