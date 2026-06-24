import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  TrendingUp,
  History,
  Radar,
  Settings2,
  Shield,
  Brain,
  Terminal,
  Activity,
  Zap,
} from 'lucide-react';

const navItems = [
  { path: '/', label: 'Overview', icon: LayoutDashboard },
  { path: '/trades', label: 'Live Trades', icon: TrendingUp },
  { path: '/history', label: 'History', icon: History },
  { path: '/scanner', label: 'Scanner', icon: Radar },
  { path: '/strategies', label: 'Strategies', icon: Settings2 },
  { path: '/risk', label: 'Risk', icon: Shield },
  { path: '/llm', label: 'AI Agent', icon: Brain },
  { path: '/diagnostics', label: 'Diagnostics', icon: Activity },
  { path: '/logs', label: 'Logs', icon: Terminal },
];

export default function Sidebar({ isConnected }) {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 glass-card rounded-none border-r border-t-0 border-b-0 border-l-0 border-r-neon-cyan/10 flex flex-col z-50">
      {/* Logo */}
      <div className="px-6 py-6 border-b border-neon-cyan/10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-neon-cyan/10 border border-neon-cyan/30 flex items-center justify-center glow-cyan">
            <Zap className="w-5 h-5 text-neon-cyan" />
          </div>
          <div>
            <h1 className="font-heading text-xl font-bold gradient-text tracking-wide">
              AutoTrader
            </h1>
            <span className="text-[10px] uppercase tracking-[0.2em] text-neon-cyan/50 font-heading font-semibold">
              Pro Edition
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group relative ${
                isActive
                  ? 'text-neon-cyan bg-neon-cyan/10 border-l-2 border-neon-cyan shadow-[inset_0_0_20px_rgba(0,240,255,0.05)]'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.03] border-l-2 border-transparent'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={`w-[18px] h-[18px] transition-all duration-200 ${
                    isActive ? 'text-neon-cyan drop-shadow-[0_0_6px_rgba(0,240,255,0.5)]' : 'text-gray-500 group-hover:text-gray-300'
                  }`}
                />
                <span className="font-heading tracking-wide">{label}</span>
                {isActive && (
                  <div className="absolute right-2 w-1.5 h-1.5 rounded-full bg-neon-cyan shadow-[0_0_8px_rgba(0,240,255,0.8)]" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-neon-cyan/10">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-600 font-mono">v1.0.0</span>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected
                  ? 'bg-neon-green shadow-[0_0_8px_rgba(0,255,136,0.6)]'
                  : 'bg-neon-red shadow-[0_0_8px_rgba(255,51,102,0.6)]'
              }`}
            />
            <span className={`text-xs ${isConnected ? 'text-neon-green/70' : 'text-neon-red/70'}`}>
              {isConnected ? 'Connected' : 'Offline'}
            </span>
          </div>
        </div>
      </div>
    </aside>
  );
}
