import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import LiveTrades from './pages/LiveTrades';
import TradeHistory from './pages/TradeHistory';
import Scanner from './pages/Scanner';
import StrategyConfig from './pages/StrategyConfig';
import RiskSettings from './pages/RiskSettings';
import LLMDecisions from './pages/LLMDecisions';
import BotLogs from './pages/BotLogs';

import Diagnostics from './pages/Diagnostics';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="trades" element={<LiveTrades />} />
        <Route path="history" element={<TradeHistory />} />
        <Route path="scanner" element={<Scanner />} />
        <Route path="strategies" element={<StrategyConfig />} />
        <Route path="risk" element={<RiskSettings />} />
        <Route path="llm" element={<LLMDecisions />} />
        <Route path="diagnostics" element={<Diagnostics />} />
        <Route path="logs" element={<BotLogs />} />
      </Route>
    </Routes>
  );
}
