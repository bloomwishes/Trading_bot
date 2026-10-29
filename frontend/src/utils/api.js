import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to inject API Key
api.interceptors.request.use(
  (config) => {
    const key = localStorage.getItem('autotrader_api_key') || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_KEY) || '';
    if (key) {
      config.headers['X-API-Key'] = key;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error?.response?.data || error.message);
    return Promise.reject(error);
  }
);

export const setApiKey = (key) => {
  if (key) {
    localStorage.setItem('autotrader_api_key', key);
  } else {
    localStorage.removeItem('autotrader_api_key');
  }
};

export const getApiKey = () => localStorage.getItem('autotrader_api_key') || '';
export const getAuthStatus = () => api.get('/auth/status');

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
export const resetPaperAccount = () => api.post('/portfolio/reset-paper');

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
// SYSTEM DIAGNOSTICS & HEALTH (AGENT 5)
// ==========================================
export const getDiagnostics = () => api.get('/diagnostics');
export const getSystemHealth = () => api.get('/status/health');

// ==========================================
// PERFORMANCE ANALYTICS & EQUITY (AGENT 5)
// ==========================================
export const getPortfolioAnalytics = (period = 'all') => api.get('/portfolio/analytics', { params: { period } });
export const getEquityCurve = (limit = 500) => api.get('/portfolio/equity-curve', { params: { limit } });

// ==========================================
// POSITION TRACKER & EXECUTION QUALITY (AGENT 3)
// ==========================================
export const getPositionTrackerPositions = () => api.get('/trades/positions');
export const getExecutionQuality = () => api.get('/trades/execution-quality');
export const getTradePerformance = () => api.get('/trades/performance');

// ==========================================
// ADVANCED RISK & CIRCUIT BREAKER (AGENT 4)
// ==========================================
export const getRiskPortfolioState = () => api.get('/risk/portfolio-state');
export const getRiskCorrelationMatrix = () => api.get('/risk/correlation-matrix');
export const triggerEmergencyShutdown = (reason = 'Manual dashboard intervention') =>
  api.post('/risk/emergency-shutdown', { reason, liquidate_positions: true });
export const resumeTrading = (reason = 'Operator verified from dashboard') =>
  api.post('/risk/resume-trading', { reason });

// ==========================================
// NEURAL NETWORK (ADAPTIVE ENGINE & BRAIN)
// ==========================================
export const getNeuralNetworkTelemetry = (limit = 50) => api.get('/strategies/shadow/predictions', { params: { limit } });
export const getNeuralModels = () => api.get('/strategies/neural_network/models');
export const trainNeuralNetwork = (pair = 'BTC/INR') => api.post('/strategies/neural_network/train', { pair });
export const trainNeuralNetworkOnHistory = (params = {}) => api.post('/strategies/neural_network/train_on_history', null, { params });
export const trainNeuralNetworkExperimental = (params = {}) => api.post('/strategies/neural_network/train_experimental', null, { params });
export const combineNeuralModels = (params = {}) => api.post('/strategies/neural_network/combine_models', null, { params });
export const getNeuralLiveBrain = (pair = 'BTC/INR', model = null) =>
  api.get('/strategies/neural_network/live_brain', { params: { pair, ...(model ? { model } : {}) } });
export const getNeuralLiveBrains = () => api.get('/strategies/neural_network/live_brains');

export const getTunnel = () => api.get('/tunnel');

export default api;

