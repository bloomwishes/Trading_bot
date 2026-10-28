import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Smartphone, ExternalLink, Copy, Check, X, ShieldCheck, Globe, Wifi } from 'lucide-react';

export default function MobileQRCodeModal({ isOpen, onClose, tunnelData }) {
  const [copied, setCopied] = useState(false);
  const [mode, setMode] = useState('cloud'); // 'cloud' | 'local'

  if (!isOpen) return null;

  const cloudUrl = tunnelData?.tunnel_url;
  const localUrl = tunnelData?.local_url || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000');
  const activeUrl = mode === 'cloud' && cloudUrl ? cloudUrl : localUrl;

  const handleCopy = () => {
    if (activeUrl) {
      navigator.clipboard.writeText(activeUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-md p-6 border rounded-2xl bg-cyber-card/95 border-neon-cyan/30 shadow-[0_0_50px_rgba(0,240,255,0.2)]">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-gray-400 rounded-lg hover:text-white hover:bg-white/10 transition-all"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2.5 rounded-xl bg-neon-cyan/10 border border-neon-cyan/20 text-neon-cyan">
            <Smartphone className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-heading font-bold text-white tracking-wide">
              Mobile Dashboard Access
            </h3>
            <p className="text-xs text-gray-400">
              Scan QR code to control AutoTrader Pro on your phone
            </p>
          </div>
        </div>

        {/* Mode Selector */}
        <div className="flex gap-2 p-1 mb-5 rounded-lg bg-cyber-bg/80 border border-white/5">
          <button
            onClick={() => setMode('cloud')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-heading font-medium transition-all ${
              mode === 'cloud'
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40 shadow-[0_0_15px_rgba(0,240,255,0.15)]'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            Cloudflare Tunnel {cloudUrl && <span className="inline-block w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />}
          </button>

          <button
            onClick={() => setMode('local')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-heading font-medium transition-all ${
              mode === 'local'
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40 shadow-[0_0_15px_rgba(0,240,255,0.15)]'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Wifi className="w-3.5 h-3.5" />
            Local Wi-Fi LAN
          </button>
        </div>

        {/* QR Code Container */}
        <div className="flex flex-col items-center justify-center p-6 mb-4 rounded-xl bg-white border border-gray-200 shadow-inner">
          {activeUrl ? (
            <QRCodeSVG
              value={activeUrl}
              size={210}
              level="H"
              includeMargin={true}
            />
          ) : (
            <div className="h-[210px] flex items-center justify-center text-sm text-gray-500 font-mono">
              Waiting for tunnel link...
            </div>
          )}
        </div>

        {/* URL Box & Actions */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-cyber-bg border border-white/10 font-mono text-xs">
            <span className="flex-1 truncate text-gray-300 select-all">
              {activeUrl || 'Tunnel initializing...'}
            </span>
            <button
              onClick={handleCopy}
              className="p-1.5 text-gray-400 rounded hover:text-neon-cyan hover:bg-white/5 transition-colors"
              title="Copy link"
            >
              {copied ? <Check className="w-4 h-4 text-neon-green" /> : <Copy className="w-4 h-4" />}
            </button>
            <a
              href={activeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-gray-400 rounded hover:text-neon-cyan hover:bg-white/5 transition-colors"
              title="Open link"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          </div>

          {/* Status Badge */}
          <div className="flex items-center justify-between text-xs text-gray-400 px-1">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-neon-green" />
              <span>
                {mode === 'cloud'
                  ? cloudUrl ? 'Live Cloudflare SSL Tunnel' : 'Starting tunnel...'
                  : 'Local Wi-Fi Network'}
              </span>
            </div>
            {copied && <span className="text-neon-green font-medium animate-fade-in">Copied to clipboard!</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
