import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  Maximize2,
  Minimize2,
  Activity,
  Sparkles,
  Cpu,
  Zap,
} from 'lucide-react';

/**
 * THREE NEURAL BRAINS 3D VISUALIZER
 *
 * One dedicated holographic brain for each neural engine:
 * 1. BTC Neural Brain (Amber Gold) - Bitcoin 10Y Macro Specialist
 * 2. ETH Neural Brain (Electric Cyan) - Ethereum Microstructure Specialist
 * 3. ALTS Neural Brain (Neon Purple) - Altcoins Volatility Basket (SOL, XRP, BNB)
 *
 * Real Neural Network Data-Driven:
 * - Neurons cleanly light up when real activation data is available.
 * - Somas glow in direct proportion to real live activations.
 * - No fake particle jumping or looping screensaver effects.
 * - Smooth 3D rotation, zoom, and interactive hover inspection.
 */

const DEG2RAD = Math.PI / 180;

function createFibonacciSphere(numPoints, radius) {
  const points = [];
  const phi = Math.PI * (3 - Math.sqrt(5)); // Golden ratio angle

  for (let i = 0; i < numPoints; i++) {
    const y = 1 - (i / (numPoints - 1 || 1)) * 2;
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;

    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;

    points.push({
      x: x * radius,
      y: y * radius,
      z: z * radius,
    });
  }
  return points;
}

const BRAIN_CONFIGS = [
  {
    key: 'btc',
    modelId: 'Neural_Network_BTC',
    name: 'BTC Neural Brain',
    pair: 'BTC/INR',
    tag: 'Macro 10Y Specialist',
    symbol: '₿',
    colorHex: '#ffaa00',
    colorGlow: 'rgba(255, 170, 0, ',
    colorBright: '#fff5cc',
    ringColor: 'rgba(255, 170, 0, 0.15)',
  },
  {
    key: 'eth',
    modelId: 'Neural_Network_ETH',
    name: 'ETH Neural Brain',
    pair: 'ETH/INR',
    tag: 'Ethereum Specialist',
    symbol: 'Ξ',
    colorHex: '#00f0ff',
    colorGlow: 'rgba(0, 240, 255, ',
    colorBright: '#e6ffff',
    ringColor: 'rgba(0, 240, 255, 0.15)',
  },
  {
    key: 'alts',
    modelId: 'Neural_Network_ALTS',
    name: 'ALTS Neural Brain',
    pair: 'SOL/INR',
    tag: 'Altcoins Basket',
    symbol: '✦',
    colorHex: '#d946ef',
    colorGlow: 'rgba(217, 70, 239, ',
    colorBright: '#fdf4ff',
    ringColor: 'rgba(217, 70, 239, 0.15)',
  },
];

export default function HolographicBrainViewer({
  btcData = null,
  ethData = null,
  altsData = null,
  activeModelId = 'Neural_Network_BTC',
  selectedPair = 'BTC/INR',
  onTriggerSurge = () => {},
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const animFrameRef = useRef(null);

  // View state: 'all' (all 3 side-by-side) | 'btc' | 'eth' | 'alts'
  const [viewMode, setViewMode] = useState('all');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);

  // Fixed 3D Perspective (Revolving & Zooming completely removed)
  const cameraRef = useRef({
    rotX: 0,
    rotY: 0,
    zoom: 1.0,
  });

  // Scene state storing nodes and axons for all 3 brains
  const sceneRef = useRef({
    brains: {
      btc: { nodes: [], axons: [] },
      eth: { nodes: [], axons: [] },
      alts: { nodes: [], axons: [] },
    },
  });

  // Build the 3D topology for each of the three brains
  const initSceneGraph = useCallback(() => {
    const scene = sceneRef.current;

    BRAIN_CONFIGS.forEach((cfg) => {
      const nodes = [];
      const key = cfg.key;

      // 1. Layer 0: 16 Input Indicator Nodes (Outer coronal ring)
      const rInput = 65;
      for (let i = 0; i < 16; i++) {
        const theta = (i / 16) * Math.PI * 2;
        nodes.push({
          id: `${key}_in_${i}`,
          brainKey: key,
          brainName: cfg.name,
          layer: 'input',
          index: i,
          name: `INDICATOR_${i}`,
          x: Math.cos(theta) * rInput,
          y: Math.sin(theta) * rInput * 0.72 + Math.sin(i * 1.5) * 8,
          z: Math.sin(theta * 2) * 22,
          baseRadius: 2.6,
          targetActivation: 0.05,
          currentActivation: 0.05,
          theme: cfg,
        });
      }

      // 2. Layer 1: 64 Hidden Cortex Neurons (Middle Fibonacci Sphere)
      const rL1 = 48;
      const l1Points = createFibonacciSphere(64, rL1);
      l1Points.forEach((pt, idx) => {
        nodes.push({
          id: `${key}_l1_${idx}`,
          brainKey: key,
          brainName: cfg.name,
          layer: 'l1',
          index: idx,
          name: `NEURON_L1_${idx}`,
          x: pt.x,
          y: pt.y,
          z: pt.z,
          baseRadius: 2.2,
          targetActivation: 0.05,
          currentActivation: 0.05,
          theme: cfg,
        });
      });

      // 3. Layer 2: 32 Hidden Synthesis Neurons (Inner Sphere)
      const rL2 = 30;
      const l2Points = createFibonacciSphere(32, rL2);
      l2Points.forEach((pt, idx) => {
        nodes.push({
          id: `${key}_l2_${idx}`,
          brainKey: key,
          brainName: cfg.name,
          layer: 'l2',
          index: idx,
          name: `NEURON_L2_${idx}`,
          x: pt.x,
          y: pt.y,
          z: pt.z,
          baseRadius: 2.4,
          targetActivation: 0.05,
          currentActivation: 0.05,
          theme: cfg,
        });
      });

      // 4. Layer 3: 3 Output Decision Heads (BUY, HOLD, SELL)
      const outConfigs = [
        { name: 'P(BUY)', offset: { x: -14, y: -8, z: 0 }, action: 'BUY' },
        { name: 'P(HOLD)', offset: { x: 0, y: 12, z: 6 }, action: 'HOLD' },
        { name: 'P(SELL)', offset: { x: 14, y: -8, z: 0 }, action: 'SELL' },
      ];
      outConfigs.forEach((c, idx) => {
        nodes.push({
          id: `${key}_out_${idx}`,
          brainKey: key,
          brainName: cfg.name,
          layer: 'output',
          index: idx,
          name: c.name,
          action: c.action,
          x: c.offset.x,
          y: c.offset.y,
          z: c.offset.z,
          baseRadius: 4.2,
          targetActivation: 0.33,
          currentActivation: 0.33,
          theme: cfg,
        });
      });

      scene.brains[key] = { nodes, axons: [] };
    });
  }, []);

  // Map incoming real live telemetry to the 3 brains
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene.brains.btc.nodes.length) {
      initSceneGraph();
    }

    const dataMap = {
      btc: btcData,
      eth: ethData,
      alts: altsData,
    };

    BRAIN_CONFIGS.forEach((cfg) => {
      const brainState = dataMap[cfg.key] || {};
      const brainObj = scene.brains[cfg.key];
      if (!brainObj) return;

      const inputs = brainState.input_features || [];
      const l1 = brainState.layer1_activations || [];
      const l2 = brainState.layer2_activations || [];
      const probs = brainState.probabilities || { BUY: 0.33, HOLD: 0.34, SELL: 0.33 };
      const selectedAction = brainState.action || 'HOLD';

      // 1. Update neuron activations (Light up based on real data)
      brainObj.nodes.forEach((node) => {
        if (node.layer === 'input') {
          const feat = inputs[node.index];
          if (feat) {
            node.name = feat.name || `INDICATOR_${node.index}`;
            node.raw_value = feat.raw_value ?? 0;
            node.targetActivation = Math.min(1.0, Math.max(0.04, Math.abs(feat.norm_value ?? 0.2)));
          }
        } else if (node.layer === 'l1') {
          const act = l1[node.index] !== undefined ? l1[node.index] : 0.05;
          node.targetActivation = Math.min(1.0, Math.max(0.04, act));
        } else if (node.layer === 'l2') {
          const act = l2[node.index] !== undefined ? l2[node.index] : 0.05;
          node.targetActivation = Math.min(1.0, Math.max(0.05, act));
        } else if (node.layer === 'output') {
          const prob = probs[node.action] !== undefined ? probs[node.action] : 0.33;
          node.targetActivation = prob;
          node.isWinning = node.action === selectedAction;
        }
      });

      // 2. Build Real Synaptic Axon Connections
      const axons = [];
      const key = cfg.key;

      // Inputs -> L1 Synapses
      const synIn = brainState.synapses_in_to_l1 || [];
      synIn.forEach((s) => {
        if (s.from < 16 && s.to < 64) {
          axons.push({
            source: `${key}_in_${s.from}`,
            target: `${key}_l1_${s.to}`,
            strength: s.strength || 0.1,
            theme: cfg,
          });
        }
      });

      // L1 -> L2 Synapses
      const synL1 = brainState.synapses_l1_to_l2 || brainState.top_synapses || [];
      synL1.forEach((s) => {
        if (s.from < 64 && s.to < 32) {
          axons.push({
            source: `${key}_l1_${s.from}`,
            target: `${key}_l2_${s.to}`,
            strength: s.strength || 0.1,
            theme: cfg,
          });
        }
      });

      // L2 -> Output Synapses
      const synOut = brainState.synapses_l2_to_out || [];
      synOut.forEach((s) => {
        if (s.from < 32 && s.to < 3) {
          axons.push({
            source: `${key}_l2_${s.from}`,
            target: `${key}_out_${s.to}`,
            strength: s.strength || 0.2,
            theme: cfg,
            isOutput: true,
          });
        }
      });

      brainObj.axons = axons;
    });
  }, [btcData, ethData, altsData, initSceneGraph]);

  // Pure Hover Proximity Inspection (No dragging, no camera rotation)
  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let closest = null;
    let minDist = 16;

    const scene = sceneRef.current;
    Object.values(scene.brains).forEach((b) => {
      b.nodes.forEach((n) => {
        if (n.projX !== undefined && n.projY !== undefined && n.projZ > 0) {
          const dist = Math.hypot(n.projX - mouseX, n.projY - mouseY);
          if (dist < minDist) {
            minDist = dist;
            closest = n;
          }
        }
      });
    });

    setHoveredNode(closest);
  };

  const handleMouseLeave = () => {
    setHoveredNode(null);
  };

  // Main 60 FPS Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    initSceneGraph();

    let frameCount = 0;

    const render = () => {
      const scene = sceneRef.current;
      const cam = cameraRef.current;

      // Handle Container Sizing (Compact 380px Viewport)
      const container = containerRef.current;
      if (container) {
        const width = container.clientWidth;
        const height = isFullscreen ? window.innerHeight - 80 : 380;
        const dpr = window.devicePixelRatio || 1;

        if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
          canvas.width = width * dpr;
          canvas.height = height * dpr;
          canvas.style.width = `${width}px`;
          canvas.style.height = `${height}px`;
        }
        ctx.resetTransform();
        ctx.scale(dpr, dpr);
      }

      const screenW = canvas.width / (window.devicePixelRatio || 1);
      const screenH = canvas.height / (window.devicePixelRatio || 1);
      const centerX = screenW / 2;
      const centerY = screenH / 2;

      // Fixed Camera: Permanently stationary front view (no revolving or zooming)
      cam.rotX = 0;
      cam.rotY = 0;
      cam.zoom = 1.0;

      // Background Clear (Cyber Tech Space)
      ctx.fillStyle = '#060810';
      ctx.fillRect(0, 0, screenW, screenH);

      // Subtle Background Glow
      const bgGrad = ctx.createRadialGradient(centerX, centerY, 40, centerX, centerY, screenW * 0.6);
      bgGrad.addColorStop(0, 'rgba(0, 240, 255, 0.03)');
      bgGrad.addColorStop(0.5, 'rgba(217, 70, 239, 0.02)');
      bgGrad.addColorStop(1, 'rgba(6, 8, 16, 0)');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, screenW, screenH);

      // 3D Perspective Math
      const focalLength = 480 * cam.zoom;
      const cameraDistance = 540;

      const cosY = Math.cos(cam.rotY);
      const sinY = Math.sin(cam.rotY);
      const cosX = Math.cos(cam.rotX);
      const sinX = Math.sin(cam.rotX);

      // Offsets for the 3 brains based on viewMode
      // In 'all' view: Left = BTC, Center = ETH, Right = ALTS
      const spacing = Math.min(205, Math.max(95, screenW * 0.25));
      const brainOffsets = {
        btc: viewMode === 'btc' ? 0 : viewMode === 'all' ? -spacing : -9999,
        eth: viewMode === 'eth' ? 0 : viewMode === 'all' ? 0 : -9999,
        alts: viewMode === 'alts' ? 0 : viewMode === 'all' ? spacing : -9999,
      };

      const scaleMultiplier = viewMode === 'all' ? 1.0 : 1.35; // Larger when focused single brain

      const projectPoint = (x, y, z, offsetX = 0) => {
        const wx = (x * scaleMultiplier) + offsetX;
        const wy = y * scaleMultiplier;
        const wz = z * scaleMultiplier;

        const x1 = wx * cosY + wz * sinY;
        const z1 = -wx * sinY + wz * cosY;

        const y2 = wy * cosX - z1 * sinX;
        const z2 = wy * sinX + z1 * cosX;

        const depth = z2 + cameraDistance;
        const scale = depth > 10 ? focalLength / depth : 0;
        return {
          sx: centerX + x1 * scale,
          sy: centerY + y2 * scale,
          depth: z2,
          scale,
        };
      };

      const allProjectedNodes = [];
      const nodeMap = new Map();

      // Project all visible brains
      BRAIN_CONFIGS.forEach((cfg) => {
        const offsetX = brainOffsets[cfg.key];
        if (offsetX < -5000) return; // Hidden in current view

        const brainObj = scene.brains[cfg.key];
        if (!brainObj) return;

        brainObj.nodes.forEach((node) => {
          const proj = projectPoint(node.x, node.y, node.z, offsetX);
          node.projX = proj.sx;
          node.projY = proj.sy;
          node.projZ = proj.depth;
          node.scale = proj.scale;
          node.offsetX = offsetX;

          // Smoothly light up neuron to target activation
          node.currentActivation += (node.targetActivation - node.currentActivation) * 0.16;

          nodeMap.set(node.id, node);
          allProjectedNodes.push(node);
        });
      });

      // ── DRAWING PASS ───────────────────────────────────────────────────────
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      // 1. Draw Volumetric Core for each active brain
      BRAIN_CONFIGS.forEach((cfg) => {
        const offsetX = brainOffsets[cfg.key];
        if (offsetX < -5000) return;

        const coreProj = projectPoint(0, 0, 0, offsetX);
        if (coreProj.scale <= 0) return;

        const coreRad = 28 * scaleMultiplier * coreProj.scale;
        const grad = ctx.createRadialGradient(
          coreProj.sx,
          coreProj.sy,
          2,
          coreProj.sx,
          coreProj.sy,
          coreRad * 2.2
        );

        grad.addColorStop(0, `${cfg.colorGlow}0.95)`);
        grad.addColorStop(0.35, `${cfg.colorGlow}0.35)`);
        grad.addColorStop(1, `${cfg.colorGlow}0)`);

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(coreProj.sx, coreProj.sy, coreRad * 2.2, 0, Math.PI * 2);
        ctx.fill();

        // Subtle Orbital Ring
        ctx.strokeStyle = cfg.ringColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(coreProj.sx, coreProj.sy, coreRad * 1.5, 0, Math.PI * 2);
        ctx.stroke();

        // 3D Floating Name Tag above brain
        const tagY = coreProj.sy - (72 * scaleMultiplier * coreProj.scale);
        ctx.fillStyle = cfg.colorHex;
        ctx.font = 'bold 11px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(`${cfg.symbol} ${cfg.name.toUpperCase()}`, coreProj.sx, tagY);
      });

      // 2. Draw Real Synaptic Axon Connections
      BRAIN_CONFIGS.forEach((cfg) => {
        const offsetX = brainOffsets[cfg.key];
        if (offsetX < -5000) return;

        const brainObj = scene.brains[cfg.key];
        if (!brainObj) return;

        brainObj.axons.forEach((axon) => {
          const s = nodeMap.get(axon.source);
          const t = nodeMap.get(axon.target);
          if (!s || !t || s.scale <= 0 || t.scale <= 0) return;

          // Axon glows when connected neurons are lit
          const avgAct = (s.currentActivation + t.currentActivation) / 2;
          if (avgAct < 0.12) return; // Keep inactive axons invisible/clean

          const alpha = Math.min(0.75, avgAct * 0.85);
          ctx.lineWidth = (axon.isOutput ? 1.4 : 0.8) * s.scale;
          ctx.strokeStyle = `${cfg.colorGlow}${alpha})`;

          ctx.beginPath();
          ctx.moveTo(s.projX, s.projY);
          ctx.lineTo(t.projX, t.projY);
          ctx.stroke();
        });
      });

      // 3. Draw Real Neurons (Turn on and light up cleanly!)
      allProjectedNodes.sort((a, b) => b.projZ - a.projZ);

      allProjectedNodes.forEach((node) => {
        if (node.scale <= 0) return;

        const act = node.currentActivation || 0.05;
        const isLit = act > 0.18; // Neuron is turned ON
        const isHigh = act > 0.55; // High excitation
        const cfg = node.theme;
        const isHovered = hoveredNode && hoveredNode.id === node.id;

        // Radius expands smoothly when turned on
        const targetR = (node.baseRadius * scaleMultiplier + act * 2.8) * node.scale;

        // Outer Glow Aura (Only shines when neuron is turned on!)
        if (isLit || node.isWinning) {
          const glowR = Math.max(5, targetR * (isHigh || node.isWinning ? 3.0 : 1.8));
          const nodeGrad = ctx.createRadialGradient(
            node.projX,
            node.projY,
            targetR * 0.2,
            node.projX,
            node.projY,
            glowR
          );

          nodeGrad.addColorStop(0, `${cfg.colorGlow}${isHigh ? 0.95 : 0.75})`);
          nodeGrad.addColorStop(0.5, `${cfg.colorGlow}0.35)`);
          nodeGrad.addColorStop(1, `${cfg.colorGlow}0)`);

          ctx.fillStyle = nodeGrad;
          ctx.beginPath();
          ctx.arc(node.projX, node.projY, glowR, 0, Math.PI * 2);
          ctx.fill();
        }

        // Solid Neuron Soma
        ctx.fillStyle = isLit || node.isWinning ? cfg.colorBright : 'rgba(100, 116, 139, 0.35)';
        ctx.beginPath();
        ctx.arc(node.projX, node.projY, Math.max(1.2, targetR * 0.65), 0, Math.PI * 2);
        ctx.fill();

        // Winning Decision Node Reticle
        if (node.isWinning) {
          ctx.strokeStyle = '#00ff88';
          ctx.lineWidth = 1.2;
          const boxSize = targetR * 2.5 + 4;
          ctx.strokeRect(node.projX - boxSize / 2, node.projY - boxSize / 2, boxSize, boxSize);
        } else if (isHovered) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.0;
          const boxSize = targetR * 2.2 + 3;
          ctx.strokeRect(node.projX - boxSize / 2, node.projY - boxSize / 2, boxSize, boxSize);
        }
      });

      ctx.restore();

      // 4. Hover Tooltip for Real Neuron
      if (hoveredNode && hoveredNode.projX !== undefined) {
        ctx.save();
        const hn = hoveredNode;
        const boxX = Math.min(screenW - 195, hn.projX + 14);
        const boxY = Math.max(12, hn.projY - 35);
        const boxW = 180;
        const boxH = 62;

        ctx.strokeStyle = hn.theme.colorHex;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hn.projX, hn.projY);
        ctx.lineTo(boxX, boxY + boxH / 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(8, 12, 22, 0.94)';
        ctx.strokeStyle = `${hn.theme.colorGlow}0.6)`;
        ctx.beginPath();
        ctx.roundRect(boxX, boxY, boxW, boxH, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = hn.theme.colorHex;
        ctx.font = 'bold 9px monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`${hn.theme.symbol} ${hn.brainName.toUpperCase()}`, boxX + 8, boxY + 15);

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 11px sans-serif';
        ctx.fillText(hn.name, boxX + 8, boxY + 30);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px monospace';
        const pct = ((hn.currentActivation || 0) * 100).toFixed(1);
        ctx.fillText(`Activation: ${pct}%`, boxX + 8, boxY + 44);

        ctx.fillStyle = hn.currentActivation > 0.18 ? '#00ff88' : '#64748b';
        ctx.fillText(
          hn.currentActivation > 0.18 ? '● LIGHT ON (ACTIVATED)' : '○ LIGHT OFF (RESTING)',
          boxX + 8,
          boxY + 56
        );

        ctx.restore();
      }

      frameCount++;
      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [viewMode, isFullscreen, hoveredNode, initSceneGraph]);

  return (
    <div
      ref={containerRef}
      className={`glass-card relative overflow-hidden border border-neon-cyan/30 shadow-[0_0_30px_rgba(0,240,255,0.06)] transition-all ${
        isFullscreen ? 'fixed inset-4 z-50 bg-[#060810]/95' : 'w-full'
      }`}
    >
      {/* Top Controls Header */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 border-b border-gray-800/80 bg-black/50 backdrop-blur-md gap-2">
        {/* Title & Live Status */}
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-neon-green opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-neon-green"></span>
          </span>
          <span className="text-xs font-bold font-heading text-white">
            TRI-ENGINE NEURAL BRAINS
          </span>
          <span className="text-[10px] text-gray-400 font-mono hidden sm:inline">
            (BTC • ETH • ALTS)
          </span>
        </div>

        {/* View Switcher: All 3 vs BTC vs ETH vs ALTS */}
        <div className="flex items-center p-0.5 rounded-lg bg-cyber-bg border border-gray-800 text-[11px]">
          <button
            onClick={() => setViewMode('all')}
            className={`px-2.5 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'all'
                ? 'bg-gradient-to-r from-amber-500/20 via-cyan-500/20 to-purple-500/20 text-white border border-white/20'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Sparkles size={11} className="text-neon-cyan" />
            <span>All 3 Brains</span>
          </button>
          <button
            onClick={() => setViewMode('btc')}
            className={`px-2 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'btc'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>₿ BTC</span>
          </button>
          <button
            onClick={() => setViewMode('eth')}
            className={`px-2 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'eth'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>Ξ ETH</span>
          </button>
          <button
            onClick={() => setViewMode('alts')}
            className={`px-2 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'alts'
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/40'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>✦ ALTS</span>
          </button>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={onTriggerSurge}
            className="px-2.5 py-1 rounded text-[11px] font-bold font-mono bg-neon-cyan/20 border border-neon-cyan/40 text-neon-cyan hover:bg-neon-cyan/30 transition-all flex items-center gap-1 shadow-[0_0_8px_rgba(0,240,255,0.2)]"
            title="Refresh and evaluate market candle data"
          >
            <Zap size={11} />
            <span>EVALUATE TICK</span>
          </button>

          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1 rounded border border-gray-700 bg-cyber-surface/60 text-gray-400 hover:text-white"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      {/* 380px Fixed Canvas Viewport (No revolving or zooming) */}
      <div className="relative select-none">
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          className="w-full h-[380px] block cursor-default"
        />

        {/* Live Decisions Telemetry Strip (Bottom) */}
        <div className="absolute bottom-3 inset-x-3 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
          {/* BTC Card */}
          <div className="px-2.5 py-1.5 rounded-lg bg-black/75 border border-amber-500/30 backdrop-blur-md text-[10px] font-mono flex items-center gap-2">
            <span className="text-amber-400 font-bold">₿ BTC:</span>
            <span
              className={`font-bold ${
                btcData?.action === 'BUY'
                  ? 'text-neon-green'
                  : btcData?.action === 'SELL'
                  ? 'text-neon-pink'
                  : 'text-gray-300'
              }`}
            >
              {btcData?.action || 'HOLD'}
            </span>
            <span className="text-gray-400">
              {((btcData?.confidence || 0.6) * 100).toFixed(0)}%
            </span>
          </div>

          {/* ETH Card */}
          <div className="px-2.5 py-1.5 rounded-lg bg-black/75 border border-cyan-500/30 backdrop-blur-md text-[10px] font-mono flex items-center gap-2">
            <span className="text-cyan-400 font-bold">Ξ ETH:</span>
            <span
              className={`font-bold ${
                ethData?.action === 'BUY'
                  ? 'text-neon-green'
                  : ethData?.action === 'SELL'
                  ? 'text-neon-pink'
                  : 'text-gray-300'
              }`}
            >
              {ethData?.action || 'HOLD'}
            </span>
            <span className="text-gray-400">
              {((ethData?.confidence || 0.6) * 100).toFixed(0)}%
            </span>
          </div>

          {/* ALTS Card */}
          <div className="px-2.5 py-1.5 rounded-lg bg-black/75 border border-purple-500/30 backdrop-blur-md text-[10px] font-mono flex items-center gap-2">
            <span className="text-purple-400 font-bold">✦ ALTS:</span>
            <span
              className={`font-bold ${
                altsData?.action === 'BUY'
                  ? 'text-neon-green'
                  : altsData?.action === 'SELL'
                  ? 'text-neon-pink'
                  : 'text-gray-300'
              }`}
            >
              {altsData?.action || 'HOLD'}
            </span>
            <span className="text-gray-400">
              {((altsData?.confidence || 0.6) * 100).toFixed(0)}%
            </span>
          </div>

          {/* Tip */}
          <div className="hidden lg:block text-[9px] font-mono text-gray-500">
            Neurons light up on live signal evaluation • Fixed Neural Engine
          </div>
        </div>
      </div>
    </div>
  );
}
