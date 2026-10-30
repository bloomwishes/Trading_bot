import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import Portfolio from './pages/Portfolio';
import LiveTrades from './pages/LiveTrades';
import TradeHistory from './pages/TradeHistory';
import Scanner from './pages/Scanner';
import StrategyConfig from './pages/StrategyConfig';
import RiskSettings from './pages/RiskSettings';
import LLMDecisions from './pages/LLMDecisions';
import NeuralBrain from './pages/NeuralBrain';
import BotLogs from './pages/BotLogs';
import AgentHub from './pages/AgentHub';
import Diagnostics from './pages/Diagnostics';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="agents" element={<AgentHub />} />
        <Route path="trades" element={<LiveTrades />} />
        <Route path="history" element={<TradeHistory />} />
        <Route path="scanner" element={<Scanner />} />
        <Route path="strategies" element={<StrategyConfig />} />
        <Route path="risk" element={<RiskSettings />} />
        <Route path="llm" element={<LLMDecisions />} />
        <Route path="neural" element={<NeuralBrain />} />
        <Route path="diagnostics" element={<Diagnostics />} />
        <Route path="logs" element={<BotLogs />} />
      </Route>
    </Routes>
  );
}
