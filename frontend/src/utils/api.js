import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error?.response?.data || error.message);
    return Promise.reject(error);
  }
);

// ==========================================
// BOT STATUS & CONTROL
// ==========================================
export const getStatus = () => api.get('/status');
export const startBot = () => api.post('/bot/start');
export const stopBot = () => api.post('/bot/stop');
export const setMode = (mode) => api.post('/bot/mode', { mode, confirm: true });

// ==========================================
// TRADES
// ==========================================
export const getOpenTrades = () => api.get('/trades/open');
export const getTradeHistory = (params) => api.get('/trades/history', { params });
export const manualTrade = (tradeData) => api.post('/trade/manual', tradeData);
export const closeTrade = (id) => api.post(`/trade/close/${id}`);
export const exportTrades = () => api.get('/trades/export', { responseType: 'blob' });

// ==========================================
// SCANNER & STRATEGIES
// ==========================================
export const getOpportunities = () => api.get('/opportunities');
export const getStrategies = () => api.get('/strategies');
export const updateStrategy = (name, data) => api.put(`/strategies/${name}`, data);

// ==========================================
// RISK MANAGEMENT
// ==========================================
export const getRiskSettings = () => api.get('/risk');
export const updateRiskSettings = (settings) => api.put('/risk', settings);

// ==========================================
// PORTFOLIO
// ==========================================
export const getPortfolioSnapshots = () => api.get('/portfolio/snapshots');
export const getPortfolioCurrent = () => api.get('/portfolio/current');

// ==========================================
// LLM DECISIONS & AI Agent
// ==========================================
export const getLLMDecisions = (params) => api.get('/llm/decisions', { params });
export const getLLMStatus = () => api.get('/llm/status');
export const closeAllTrades = () => api.post('/trades/close-all');

// ==========================================
// LIVE MARKET & AI ANALYSIS
// ==========================================
export const getLiveMarket = () => api.get('/market/live');
export const getAIAnalysis = (symbols) => api.get('/market/analyze', { params: { symbols }, timeout: 65000 });

// ==========================================
// SYSTEM DIAGNOSTICS
// ==========================================
export const getDiagnostics = () => api.get('/diagnostics');

export default api;
