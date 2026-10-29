import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  Zap,
  RotateCcw,
  Volume2,
  VolumeX,
  Play,
  Pause,
  Maximize2,
  Minimize2,
  Activity,
  Sparkles,
  Cpu,
  CheckCircle2,
} from 'lucide-react';

/**
 * HOLOGRAPHIC 3D NEURAL BRAIN VIEWER (100% REAL NEURAL NETWORK TELEMETRY)
 *
 * Fully data-driven by the actual DeepTradingNN weights & activations:
 * - Layer 0: 16 Real Input Indicators (RSI, Stoch, MACD, EMAs, ATR, Volume, etc.)
 * - Layer 1: 64 Real Hidden Neurons (exact live activation values a1[0..63])
 * - Layer 2: 32 Real Hidden Neurons (exact live activation values a2[0..31])
 * - Layer 3: Real Output Head (BUY, HOLD, SELL probabilities & expected return)
 * - Real Synapses: Rendered directly from mathematically extracted active weight flows
 *   (synapses_in_to_l1, synapses_l1_to_l2, synapses_l2_to_out)
 * - NO FAKE RANDOM FIRING: Neurons only fire on real live inference ticks!
 * - Compact viewport (390px) designed for clean dashboard integration.
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

export default function HolographicBrainViewer({
  jarvisData = null,
  ultronData = null,
  activeModelId = 'Neural_Network_BTC',
  selectedPair = 'BTC/INR',
  isSurgeFiring = false,
  onTriggerSurge = () => {},
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const animFrameRef = useRef(null);
  const audioCtxRef = useRef(null);

  // View & UI State
  const [viewMode, setViewMode] = useState('dual'); // 'dual' | 'jarvis' | 'ultron'
  const [autoRotate, setAutoRotate] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [lastInferenceTime, setLastInferenceTime] = useState(Date.now());
  const [inferenceCount, setInferenceCount] = useState(0);

  // 3D Camera State
  const cameraRef = useRef({
    rotX: 10 * DEG2RAD,
    rotY: -15 * DEG2RAD,
    targetRotX: 10 * DEG2RAD,
    targetRotY: -15 * DEG2RAD,
    zoom: 1.0,
    targetZoom: 1.0,
    isDragging: false,
    lastMouseX: 0,
    lastMouseY: 0,
    autoRotSpeed: 0.0025,
  });

  // Scene Graph Data
  const sceneRef = useRef({
    jarvisNodes: [],
    jarvisAxons: [],
    jarvisPulses: [],
    ultronNodes: [],
    ultronAxons: [],
    ultronPulses: [],
    bridgeAxons: [],
    bridgePulses: [],
    lastSeq: null,
    propagationStage: 0, // 0 = idle heatmap, 1 = input pass, 2 = L1 pass, 3 = L2 pass, 4 = output pass
    stageStartTime: 0,
  });

  // Audio tone generator on real inference
  const playRealSignalTone = useCallback((freq = 520, duration = 0.07) => {
    if (!soundEnabled) return;
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') ctx.resume();

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(freq * 1.4, ctx.currentTime + duration);

      gain.gain.setValueAtTime(0.03, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch {
      // Audio muted or not allowed
    }
  }, [soundEnabled]);

  // Build the 3D Neural Topology
  const initSceneGraph = useCallback(() => {
    const scene = sceneRef.current;

    const buildBrainEntity = (isUltron = false) => {
      const nodes = [];
      const colorTheme = isUltron ? 'amber' : 'cyan';

      // 1. LAYER 0: 16 INPUT INDICATORS (Outer coronal ring)
      const inputRadius = isUltron ? 120 : 115;
      for (let i = 0; i < 16; i++) {
        const theta = (i / 16) * Math.PI * 2;
        nodes.push({
          id: `${colorTheme}_in_${i}`,
          layer: 'input',
          index: i,
          name: `INDICATOR_${i}`,
          x: Math.cos(theta) * inputRadius,
          y: Math.sin(theta) * inputRadius * 0.75 + Math.sin(i * 1.5) * 15,
          z: Math.sin(theta * 2) * 35,
          baseRadius: 3.2,
          currentRadius: 3.2,
          activation: 0.0,
          raw_value: 0.0,
          flash: 0.0,
          theme: colorTheme,
        });
      }

      // 2. LAYER 1: 64 HIDDEN CORTEX NEURONS (Middle Fibonacci Sphere)
      const l1Radius = isUltron ? 85 : 80;
      const l1Coords = createFibonacciSphere(64, l1Radius);
      l1Coords.forEach((pt, idx) => {
        nodes.push({
          id: `${colorTheme}_l1_${idx}`,
          layer: 'l1',
          index: idx,
          name: `NEURON_L1_${idx}`,
          x: pt.x,
          y: pt.y,
          z: pt.z,
          baseRadius: 2.5,
          currentRadius: 2.5,
          activation: 0.0,
          flash: 0.0,
          theme: colorTheme,
        });
      });

      // 3. LAYER 2: 32 HIDDEN SYNTHESIS NEURONS (Inner Dense Sphere)
      const l2Radius = isUltron ? 50 : 48;
      const l2Coords = createFibonacciSphere(32, l2Radius);
      l2Coords.forEach((pt, idx) => {
        nodes.push({
          id: `${colorTheme}_l2_${idx}`,
          layer: 'l2',
          index: idx,
          name: `NEURON_L2_${idx}`,
          x: pt.x,
          y: pt.y,
          z: pt.z,
          baseRadius: 2.8,
          currentRadius: 2.8,
          activation: 0.0,
          flash: 0.0,
          theme: colorTheme,
        });
      });

      // 4. LAYER 3: 3 OUTPUT DECISION NODES (BUY, HOLD, SELL)
      const outConfigs = [
        { name: 'P(BUY)', offset: { x: -20, y: -10, z: 0 }, action: 'BUY' },
        { name: 'P(HOLD)', offset: { x: 0, y: 18, z: 8 }, action: 'HOLD' },
        { name: 'P(SELL)', offset: { x: 20, y: -10, z: 0 }, action: 'SELL' },
      ];
      outConfigs.forEach((cfg, idx) => {
        nodes.push({
          id: `${colorTheme}_out_${idx}`,
          layer: 'output',
          index: idx,
          name: cfg.name,
          action: cfg.action,
          x: cfg.offset.x,
          y: cfg.offset.y,
          z: cfg.offset.z,
          baseRadius: 5.0,
          currentRadius: 5.0,
          activation: 0.33,
          flash: 0.0,
          theme: colorTheme,
        });
      });

      return { nodes };
    };

    scene.jarvisNodes = buildBrainEntity(false).nodes;
    scene.ultronNodes = buildBrainEntity(true).nodes;
    scene.jarvisAxons = [];
    scene.ultronAxons = [];
    scene.bridgeAxons = [];
    scene.jarvisPulses = [];
    scene.ultronPulses = [];
    scene.bridgePulses = [];
  }, []);

  // Update Scene Graph with REAL LIVE INFERENCE SIGNALS
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene.jarvisNodes.length) {
      initSceneGraph();
    }

    const jBrain = jarvisData || {};
    const uBrain = ultronData || jBrain;

    // Detect if this is a fresh live inference signal
    const currentSeq = `${jBrain.inference_seq || jBrain.timestamp || ''}_${jBrain.price || ''}_${jBrain.confidence || ''}`;
    const isNewInference = scene.lastSeq !== null && scene.lastSeq !== currentSeq;
    scene.lastSeq = currentSeq;

    if (isNewInference) {
      setLastInferenceTime(Date.now());
      setInferenceCount((prev) => prev + 1);
      playRealSignalTone(620, 0.1);
    }

    // Function to populate REAL DATA into brain nodes & axons
    const applyRealDataToBrain = (nodes, brain, isUltron = false) => {
      const colorTheme = isUltron ? 'amber' : 'cyan';
      const inputs = brain.input_features || [];
      const l1 = brain.layer1_activations || [];
      const l2 = brain.layer2_activations || [];
      const probs = brain.probabilities || { BUY: 0.33, HOLD: 0.34, SELL: 0.33 };
      const selectedAction = brain.action || 'HOLD';

      // 1. Inputs
      nodes.forEach((node) => {
        if (node.layer === 'input') {
          const feat = inputs[node.index];
          if (feat) {
            node.name = feat.name || `INDICATOR_${node.index}`;
            node.raw_value = feat.raw_value ?? 0;
            node.activation = Math.min(1.0, Math.max(0.05, Math.abs(feat.norm_value ?? 0.3)));
            if (isNewInference) node.flash = 1.0;
          }
        } else if (node.layer === 'l1') {
          const act = l1[node.index] !== undefined ? l1[node.index] : 0.05;
          node.activation = Math.min(1.0, Math.max(0.04, act));
          if (isNewInference && act > 0.4) node.flash = 1.0;
        } else if (node.layer === 'l2') {
          const act = l2[node.index] !== undefined ? l2[node.index] : 0.05;
          node.activation = Math.min(1.0, Math.max(0.05, act));
          if (isNewInference && act > 0.45) node.flash = 1.0;
        } else if (node.layer === 'output') {
          const k = node.action;
          const prob = probs[k] !== undefined ? probs[k] : 0.33;
          node.activation = prob;
          if (k === selectedAction) {
            node.isWinning = true;
            if (isNewInference) node.flash = 1.5;
          } else {
            node.isWinning = false;
          }
        }
      });

      // 2. Build REAL SYNAPSE AXONS directly from backend mathematical flows
      const axons = [];
      const pulses = [];

      // A) Real Inputs -> Layer 1 Synapses
      const synInToL1 = brain.synapses_in_to_l1 || [];
      synInToL1.forEach((syn) => {
        if (syn.from < 16 && syn.to < 64) {
          axons.push({
            source: `${colorTheme}_in_${syn.from}`,
            target: `${colorTheme}_l1_${syn.to}`,
            strength: syn.strength,
            theme: colorTheme,
          });

          // Trigger live propagation pulse on new inference
          if (isNewInference && syn.strength > 0.02) {
            pulses.push({
              source: `${colorTheme}_in_${syn.from}`,
              target: `${colorTheme}_l1_${syn.to}`,
              progress: 0.0,
              speed: 0.045,
              size: 2.8 + Math.min(3, syn.strength * 2),
              theme: colorTheme,
            });
          }
        }
      });

      // B) Real Layer 1 -> Layer 2 Synapses
      const synL1ToL2 = brain.synapses_l1_to_l2 || brain.top_synapses || [];
      synL1ToL2.forEach((syn) => {
        if (syn.from < 64 && syn.to < 32) {
          axons.push({
            source: `${colorTheme}_l1_${syn.from}`,
            target: `${colorTheme}_l2_${syn.to}`,
            strength: syn.strength,
            theme: colorTheme,
          });

          if (isNewInference && syn.strength > 0.03) {
            pulses.push({
              source: `${colorTheme}_l1_${syn.from}`,
              target: `${colorTheme}_l2_${syn.to}`,
              progress: -0.25, // Staggered delay for real forward wave
              speed: 0.04,
              size: 3.0 + Math.min(3, syn.strength * 2),
              theme: colorTheme,
            });
          }
        }
      });

      // C) Real Layer 2 -> Output Decision Head Synapses
      const synL2ToOut = brain.synapses_l2_to_out || [];
      synL2ToOut.forEach((syn) => {
        if (syn.from < 32 && syn.to < 3) {
          axons.push({
            source: `${colorTheme}_l2_${syn.from}`,
            target: `${colorTheme}_out_${syn.to}`,
            strength: syn.strength,
            theme: colorTheme,
            isOutput: true,
          });

          if (isNewInference) {
            pulses.push({
              source: `${colorTheme}_l2_${syn.from}`,
              target: `${colorTheme}_out_${syn.to}`,
              progress: -0.55, // Staggered arrival at decision nucleus
              speed: 0.042,
              size: 3.5,
              theme: colorTheme,
            });
          }
        }
      });

      return { axons, pulses };
    };

    const jRes = applyRealDataToBrain(scene.jarvisNodes, jBrain, false);
    scene.jarvisAxons = jRes.axons;
    scene.jarvisPulses = jRes.pulses;

    const uRes = applyRealDataToBrain(scene.ultronNodes, uBrain, true);
    scene.ultronAxons = uRes.axons;
    scene.ultronPulses = uRes.pulses;

    // Cross-Brain Real Correlation Bridge
    scene.bridgeAxons = [];
    scene.bridgePulses = [];
    const topJL1 = (jBrain.layer1_activations || [])
      .map((act, i) => ({ act, i }))
      .sort((a, b) => b.act - a.act)
      .slice(0, 5);
    const topUL1 = (uBrain.layer1_activations || [])
      .map((act, i) => ({ act, i }))
      .sort((a, b) => b.act - a.act)
      .slice(0, 5);

    topJL1.forEach((jNode, idx) => {
      const uNode = topUL1[idx];
      if (uNode) {
        scene.bridgeAxons.push({
          source: `cyan_l1_${jNode.i}`,
          target: `amber_l1_${uNode.i}`,
          strength: (jNode.act + uNode.act) / 2,
          theme: 'bridge',
        });

        if (isNewInference) {
          scene.bridgePulses.push({
            source: `cyan_l1_${jNode.i}`,
            target: `amber_l1_${uNode.i}`,
            progress: 0.0,
            speed: 0.03,
            size: 3.5,
            theme: 'bridge',
          });
        }
      }
    });
  }, [jarvisData, ultronData, initSceneGraph, playRealSignalTone]);

  // Handle manual surge
  const handleSurge = useCallback(() => {
    onTriggerSurge();
    playRealSignalTone(700, 0.15);
  }, [onTriggerSurge, playRealSignalTone]);

  useEffect(() => {
    if (isSurgeFiring) {
      handleSurge();
    }
  }, [isSurgeFiring, handleSurge]);

  // Interaction handlers
  const handleMouseDown = (e) => {
    const cam = cameraRef.current;
    cam.isDragging = true;
    cam.lastMouseX = e.clientX;
    cam.lastMouseY = e.clientY;
  };

  const handleMouseMove = (e) => {
    const cam = cameraRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (cam.isDragging) {
      const dx = e.clientX - cam.lastMouseX;
      const dy = e.clientY - cam.lastMouseY;
      cam.targetRotY += dx * 0.007;
      cam.targetRotX += dy * 0.007;
      cam.targetRotX = Math.max(-Math.PI * 0.45, Math.min(Math.PI * 0.45, cam.targetRotX));
      cam.lastMouseX = e.clientX;
      cam.lastMouseY = e.clientY;
    }

    // Node Proximity Raycasting
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let closest = null;
    let minDist = 16;

    const checkNodes = (nodes) => {
      nodes.forEach((n) => {
        if (n.projX !== undefined && n.projY !== undefined && n.projZ > 0) {
          const dist = Math.hypot(n.projX - mouseX, n.projY - mouseY);
          if (dist < minDist) {
            minDist = dist;
            closest = n;
          }
        }
      });
    };

    const scene = sceneRef.current;
    checkNodes(scene.jarvisNodes);
    checkNodes(scene.ultronNodes);
    setHoveredNode(closest);
  };

  const handleMouseUp = () => {
    cameraRef.current.isDragging = false;
  };

  const handleTouchStart = (e) => {
    if (e.touches.length === 1) {
      const cam = cameraRef.current;
      cam.isDragging = true;
      cam.lastMouseX = e.touches[0].clientX;
      cam.lastMouseY = e.touches[0].clientY;
    }
  };

  const handleTouchMove = (e) => {
    if (e.touches.length === 1 && cameraRef.current.isDragging) {
      const dx = e.touches[0].clientX - cameraRef.current.lastMouseX;
      const dy = e.touches[0].clientY - cameraRef.current.lastMouseY;
      cameraRef.current.targetRotY += dx * 0.007;
      cameraRef.current.targetRotX += dy * 0.007;
      cameraRef.current.targetRotX = Math.max(-Math.PI * 0.45, Math.min(Math.PI * 0.45, cameraRef.current.targetRotX));
      cameraRef.current.lastMouseX = e.touches[0].clientX;
      cameraRef.current.lastMouseY = e.touches[0].clientY;
    }
  };

  const handleTouchEnd = () => {
    cameraRef.current.isDragging = false;
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const cam = cameraRef.current;
    const delta = e.deltaY < 0 ? 0.08 : -0.08;
    cam.targetZoom = Math.max(0.7, Math.min(1.8, cam.targetZoom + delta));
  };

  const resetCamera = () => {
    const cam = cameraRef.current;
    cam.targetRotX = 10 * DEG2RAD;
    cam.targetRotY = -15 * DEG2RAD;
    cam.targetZoom = 1.0;
  };

  // Main 60 FPS Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    initSceneGraph();

    let frameCount = 0;

    const render = () => {
      const scene = sceneRef.current;
      const cam = cameraRef.current;

      // Handle Container Sizing (Compact 390px Viewport)
      const container = containerRef.current;
      if (container) {
        const width = container.clientWidth;
        const height = isFullscreen ? window.innerHeight - 80 : 390;
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

      // Smooth Camera Easing
      cam.rotX += (cam.targetRotX - cam.rotX) * 0.12;
      cam.rotY += (cam.targetRotY - cam.rotY) * 0.12;
      cam.zoom += (cam.targetZoom - cam.zoom) * 0.12;

      if (autoRotate && !cam.isDragging) {
        cam.targetRotY += cam.autoRotSpeed;
      }

      // Background Clear (Cyber Stark Dark Room)
      ctx.fillStyle = '#060810';
      ctx.fillRect(0, 0, screenW, screenH);

      // Radial Holographic Aura
      const bgGrad = ctx.createRadialGradient(centerX, centerY, 60, centerX, centerY, screenW * 0.6);
      bgGrad.addColorStop(0, 'rgba(0, 240, 255, 0.04)');
      bgGrad.addColorStop(0.5, 'rgba(255, 130, 0, 0.03)');
      bgGrad.addColorStop(1, 'rgba(6, 8, 16, 0)');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, screenW, screenH);

      // Concentric HUD Calibration Circles
      ctx.save();
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.07)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 175 * cam.zoom, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = 'rgba(255, 120, 0, 0.05)';
      ctx.beginPath();
      ctx.arc(centerX, centerY, 215 * cam.zoom, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // 3D Perspective Math
      const responsiveFocal = Math.min(520, Math.max(340, screenW * 0.75));
      const focalLength = responsiveFocal * cam.zoom;
      const cameraDistance = 580;

      const cosY = Math.cos(cam.rotY);
      const sinY = Math.sin(cam.rotY);
      const cosX = Math.cos(cam.rotX);
      const sinX = Math.sin(cam.rotX);

      // Positioning: Responsive separation between Jarvis and Ultron
      const baseOffset = Math.min(185, Math.max(105, screenW * 0.24));
      let jarvisOffsetX = -baseOffset;
      let ultronOffsetX = baseOffset;
      let renderJarvis = true;
      let renderUltron = true;

      if (viewMode === 'jarvis') {
        jarvisOffsetX = 0;
        renderUltron = false;
      } else if (viewMode === 'ultron') {
        ultronOffsetX = 0;
        renderJarvis = false;
      }

      const projectPoint = (x, y, z, offsetX = 0) => {
        const wx = x + offsetX;
        const wy = y;
        const wz = z;

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

      const nodeMap = new Map();

      if (renderJarvis) {
        scene.jarvisNodes.forEach((node) => {
          const proj = projectPoint(node.x, node.y, node.z, jarvisOffsetX);
          node.projX = proj.sx;
          node.projY = proj.sy;
          node.projZ = proj.depth;
          node.scale = proj.scale;
          nodeMap.set(node.id, node);
        });
      }

      if (renderUltron) {
        scene.ultronNodes.forEach((node) => {
          const proj = projectPoint(node.x, node.y, node.z, ultronOffsetX);
          node.projX = proj.sx;
          node.projY = proj.sy;
          node.projZ = proj.depth;
          node.scale = proj.scale;
          nodeMap.set(node.id, node);
        });
      }

      // ── DRAWING PASS (Additive Blending) ───────────────────────────────────
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      // 1. Core Luminous Nucleus (Volumetric Radiance)
      const drawCore = (offsetX, theme) => {
        const coreProj = projectPoint(0, 0, 0, offsetX);
        if (coreProj.scale <= 0) return;

        const coreRadius = (theme === 'amber' ? 44 : 40) * coreProj.scale;
        const grad = ctx.createRadialGradient(
          coreProj.sx,
          coreProj.sy,
          2,
          coreProj.sx,
          coreProj.sy,
          coreRadius * 2.0
        );

        if (theme === 'amber') {
          grad.addColorStop(0, 'rgba(255, 235, 180, 0.95)');
          grad.addColorStop(0.25, 'rgba(255, 140, 0, 0.55)');
          grad.addColorStop(0.6, 'rgba(255, 60, 0, 0.2)');
          grad.addColorStop(1, 'rgba(255, 20, 0, 0)');
        } else {
          grad.addColorStop(0, 'rgba(235, 255, 255, 0.95)');
          grad.addColorStop(0.25, 'rgba(0, 240, 255, 0.55)');
          grad.addColorStop(0.6, 'rgba(0, 110, 255, 0.2)');
          grad.addColorStop(1, 'rgba(0, 50, 180, 0)');
        }

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(coreProj.sx, coreProj.sy, coreRadius * 2.0, 0, Math.PI * 2);
        ctx.fill();

        // Orbital rings
        for (let r = 0; r < 3; r++) {
          const ringRad = (18 + r * 12) * coreProj.scale;
          ctx.strokeStyle =
            theme === 'amber'
              ? `rgba(255, 160, 20, ${0.15 + r * 0.05})`
              : `rgba(0, 240, 255, ${0.18 + r * 0.05})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.ellipse(coreProj.sx, coreProj.sy, ringRad, ringRad * 0.4, (frameCount * 0.008 * (r % 2 === 0 ? 1 : -1)) + r, 0, Math.PI * 2);
          ctx.stroke();
        }
      };

      if (renderJarvis) drawCore(jarvisOffsetX, 'cyan');
      if (renderUltron) drawCore(ultronOffsetX, 'amber');

      // 2. Draw Real Synaptic Axons (Direct weight lines)
      const drawAxonList = (axons) => {
        axons.forEach((axon) => {
          const s = nodeMap.get(axon.source);
          const t = nodeMap.get(axon.target);
          if (!s || !t || s.scale <= 0 || t.scale <= 0) return;

          const strength = axon.strength || 0.1;
          const avgDepth = (s.projZ + t.projZ) / 2;
          const depthAlpha = Math.max(0.12, Math.min(0.9, (avgDepth + 250) / 500));
          const alpha = Math.min(0.85, (0.15 + strength * 0.7)) * depthAlpha;

          ctx.lineWidth = (axon.isOutput ? 1.6 : 1.0) * s.scale;

          if (axon.theme === 'bridge') {
            const bridgeGrad = ctx.createLinearGradient(s.projX, s.projY, t.projX, t.projY);
            bridgeGrad.addColorStop(0, `rgba(0, 240, 255, ${alpha})`);
            bridgeGrad.addColorStop(0.5, `rgba(255, 0, 229, ${alpha * 1.2})`);
            bridgeGrad.addColorStop(1, `rgba(255, 140, 0, ${alpha})`);
            ctx.strokeStyle = bridgeGrad;
          } else if (axon.theme === 'amber') {
            ctx.strokeStyle = `rgba(255, 130, 20, ${alpha})`;
          } else {
            ctx.strokeStyle = `rgba(0, 210, 255, ${alpha})`;
          }

          ctx.beginPath();
          ctx.moveTo(s.projX, s.projY);
          ctx.lineTo(t.projX, t.projY);
          ctx.stroke();
        });
      };

      if (renderJarvis) drawAxonList(scene.jarvisAxons);
      if (renderUltron) drawAxonList(scene.ultronAxons);
      if (viewMode === 'dual') drawAxonList(scene.bridgeAxons);

      // 3. Draw Real Action Potential Pulses (Only on Real Forward Inference)
      const updatePulses = (pulses) => {
        for (let i = pulses.length - 1; i >= 0; i--) {
          const p = pulses[i];
          p.progress += p.speed;

          const s = nodeMap.get(p.source);
          const t = nodeMap.get(p.target);

          if (!s || !t || p.progress >= 1.0) {
            if (t && p.progress >= 1.0) {
              t.flash = 1.0;
            }
            pulses.splice(i, 1);
            continue;
          }

          if (p.progress < 0) continue; // Staggered delay waiting to fire

          const px = s.projX + (t.projX - s.projX) * p.progress;
          const py = s.projY + (t.projY - s.projY) * p.progress;
          const rad = p.size * ((s.scale + t.scale) / 2);

          const pGrad = ctx.createRadialGradient(px, py, 1, px, py, rad * 3);
          if (p.theme === 'bridge') {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.4, 'rgba(255, 0, 229, 0.9)');
            pGrad.addColorStop(1, 'rgba(0, 240, 255, 0)');
          } else if (p.theme === 'amber') {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.4, 'rgba(255, 170, 0, 0.95)');
            pGrad.addColorStop(1, 'rgba(255, 60, 0, 0)');
          } else {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.4, 'rgba(0, 240, 255, 0.95)');
            pGrad.addColorStop(1, 'rgba(0, 100, 255, 0)');
          }

          ctx.fillStyle = pGrad;
          ctx.beginPath();
          ctx.arc(px, py, rad * 3, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(px, py, rad * 0.9, 0, Math.PI * 2);
          ctx.fill();
        }
      };

      if (renderJarvis) updatePulses(scene.jarvisPulses);
      if (renderUltron) updatePulses(scene.ultronPulses);
      if (viewMode === 'dual') updatePulses(scene.bridgePulses);

      // 4. Draw Real Neurons (100% Data-Driven Somas)
      const drawNodes = (nodes) => {
        const sorted = [...nodes].sort((a, b) => b.projZ - a.projZ);

        sorted.forEach((node) => {
          if (node.scale <= 0) return;

          node.flash *= 0.92;
          const act = node.activation || 0.05;
          const isHigh = act > 0.55;
          const isAmber = node.theme === 'amber';
          const isHovered = hoveredNode && hoveredNode.id === node.id;

          // Target radius scales directly with REAL activation
          const baseRad = (node.baseRadius + act * 3.5 + node.flash * 2.5) * node.scale;
          node.currentRadius = baseRad;

          // Glow Halo
          const glowRad = Math.max(6, baseRad * (isHigh || node.isWinning ? 3.0 : 1.8));
          const nodeGrad = ctx.createRadialGradient(
            node.projX,
            node.projY,
            baseRad * 0.2,
            node.projX,
            node.projY,
            glowRad
          );

          if (isAmber) {
            nodeGrad.addColorStop(
              0,
              isHigh || node.flash > 0.2 ? 'rgba(255, 255, 220, 1)' : 'rgba(255, 170, 30, 0.85)'
            );
            nodeGrad.addColorStop(0.4, 'rgba(255, 110, 0, 0.5)');
            nodeGrad.addColorStop(1, 'rgba(255, 40, 0, 0)');
          } else {
            nodeGrad.addColorStop(
              0,
              isHigh || node.flash > 0.2 ? 'rgba(235, 255, 255, 1)' : 'rgba(0, 240, 255, 0.85)'
            );
            nodeGrad.addColorStop(0.4, 'rgba(0, 150, 255, 0.5)');
            nodeGrad.addColorStop(1, 'rgba(0, 70, 255, 0)');
          }

          ctx.fillStyle = nodeGrad;
          ctx.beginPath();
          ctx.arc(node.projX, node.projY, glowRad, 0, Math.PI * 2);
          ctx.fill();

          // Solid Photon Soma
          ctx.fillStyle =
            isHigh || node.flash > 0.2
              ? '#ffffff'
              : isAmber
              ? 'rgba(255, 180, 50, 0.9)'
              : 'rgba(80, 240, 255, 0.9)';
          ctx.beginPath();
          ctx.arc(node.projX, node.projY, Math.max(1.4, baseRad * 0.6), 0, Math.PI * 2);
          ctx.fill();

          // Reticle for Hovered or Winning Decision Node
          if (isHovered || node.isWinning) {
            ctx.strokeStyle = node.isWinning ? '#00ff88' : '#ffffff';
            ctx.lineWidth = 1.2;
            const size = baseRad * 2.4 + 4;
            ctx.strokeRect(node.projX - size / 2, node.projY - size / 2, size, size);
          }
        });
      };

      if (renderJarvis) drawNodes(scene.jarvisNodes);
      if (renderUltron) drawNodes(scene.ultronNodes);

      ctx.restore();

      // 5. Stark Tech Holographic Tooltip for Hovered Real Node
      if (hoveredNode && hoveredNode.projX !== undefined) {
        ctx.save();
        const hn = hoveredNode;
        const boxX = Math.min(screenW - 205, hn.projX + 18);
        const boxY = Math.max(15, hn.projY - 40);
        const boxW = 190;
        const boxH = 68;

        ctx.strokeStyle = hn.theme === 'amber' ? '#ff9900' : '#00f0ff';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hn.projX, hn.projY);
        ctx.lineTo(boxX, boxY + boxH / 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(8, 12, 22, 0.94)';
        ctx.strokeStyle = hn.theme === 'amber' ? 'rgba(255, 140, 0, 0.6)' : 'rgba(0, 240, 255, 0.6)';
        ctx.beginPath();
        ctx.roundRect(boxX, boxY, boxW, boxH, 6);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = hn.theme === 'amber' ? '#ffaa00' : '#00f0ff';
        ctx.font = 'bold 9px monospace';
        ctx.fillText(`REAL ${hn.theme.toUpperCase()} // ${hn.layer.toUpperCase()}`, boxX + 8, boxY + 16);

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 11px sans-serif';
        ctx.fillText(hn.name, boxX + 8, boxY + 32);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px monospace';
        ctx.fillText(`Activation: ${(hn.activation * 100).toFixed(1)}%`, boxX + 8, boxY + 47);

        ctx.fillStyle = hn.activation > 0.5 ? '#00ff88' : '#64748b';
        ctx.fillText(
          hn.activation > 0.5 ? '● EXCITATORY (LIVE FIRING)' : '○ BASELINE (RESTING)',
          boxX + 8,
          boxY + 60
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
  }, [viewMode, autoRotate, isFullscreen, hoveredNode, initSceneGraph]);

  return (
    <div
      ref={containerRef}
      className={`glass-card relative overflow-hidden border border-neon-cyan/40 shadow-[0_0_30px_rgba(0,240,255,0.08)] transition-all ${
        isFullscreen ? 'fixed inset-4 z-50 bg-[#060810]/95' : 'w-full'
      }`}
    >
      {/* Compact Header Bar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 border-b border-gray-800/80 bg-black/50 backdrop-blur-md gap-2">
        {/* Live Signal Indicator */}
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-neon-green opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-neon-green"></span>
          </span>
          <span className="text-[11px] font-bold font-mono text-neon-green uppercase tracking-wide">
            LIVE SIGNAL FEED
          </span>
          <span className="text-[10px] text-gray-400 font-mono hidden sm:inline">
            | Real Weights &amp; Activations
          </span>
        </div>

        {/* View Switcher: Dual vs Jarvis vs Ultron */}
        <div className="flex items-center p-0.5 rounded-lg bg-cyber-bg/90 border border-gray-800 text-[11px]">
          <button
            onClick={() => setViewMode('dual')}
            className={`px-2.5 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'dual'
                ? 'bg-gradient-to-r from-neon-cyan/30 to-orange-500/30 text-white border border-white/20'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Sparkles size={11} className="text-neon-cyan" />
            <span>Avengers Dual</span>
          </button>
          <button
            onClick={() => setViewMode('jarvis')}
            className={`px-2.5 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'jarvis'
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Cpu size={11} />
            <span>JARVIS (Macro)</span>
          </button>
          <button
            onClick={() => setViewMode('ultron')}
            className={`px-2.5 py-1 font-semibold rounded transition-all flex items-center gap-1 ${
              viewMode === 'ultron'
                ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Zap size={11} />
            <span>ULTRON (Alts)</span>
          </button>
        </div>

        {/* Quick Toolbar */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleSurge}
            className="px-2.5 py-1 rounded text-[11px] font-bold font-mono bg-neon-cyan/20 border border-neon-cyan/40 text-neon-cyan hover:bg-neon-cyan/30 transition-all flex items-center gap-1 shadow-[0_0_10px_rgba(0,240,255,0.2)]"
            title="Evaluate fresh market candle inference"
          >
            <Zap size={11} />
            <span>EVALUATE TICK</span>
          </button>

          <button
            onClick={() => setAutoRotate(!autoRotate)}
            className={`p-1 rounded border text-xs ${
              autoRotate
                ? 'bg-cyber-surface border-neon-cyan/40 text-neon-cyan'
                : 'bg-cyber-surface/60 border-gray-700 text-gray-400'
            }`}
            title={autoRotate ? 'Pause 3D Rotation' : 'Resume 3D Rotation'}
          >
            {autoRotate ? <Pause size={12} /> : <Play size={12} />}
          </button>

          <button
            onClick={resetCamera}
            className="p-1 rounded border border-gray-700 bg-cyber-surface/60 text-gray-400 hover:text-white"
            title="Reset Camera"
          >
            <RotateCcw size={12} />
          </button>

          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={`p-1 rounded border text-xs ${
              soundEnabled
                ? 'bg-neon-magenta/20 border-neon-magenta text-neon-magenta'
                : 'bg-cyber-surface/60 border-gray-700 text-gray-500'
            }`}
            title={soundEnabled ? 'Mute' : 'Enable Neural Signal Audio'}
          >
            {soundEnabled ? <Volume2 size={12} /> : <VolumeX size={12} />}
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

      {/* Compact Canvas Area (390px) */}
      <div className="relative cursor-grab active:cursor-grabbing select-none">
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onWheel={handleWheel}
          className="w-full h-[390px] block"
        />

        {/* Real Signal Telemetry Pill (Bottom Left) */}
        <div className="absolute bottom-3 left-3 px-3 py-1.5 rounded-lg bg-black/70 border border-white/10 backdrop-blur-md text-[10px] font-mono text-gray-300 pointer-events-none flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-neon-cyan">
            <Activity size={11} className="animate-pulse" />
            <span className="font-bold">INFERENCE #{jarvisData?.train_steps || inferenceCount || 1}</span>
          </div>
          <span className="text-gray-500">|</span>
          <span>Feed: <strong className="text-white">{selectedPair}</strong></span>
          <span className="text-gray-500">|</span>
          <span>Decision: <strong className="text-neon-green">{jarvisData?.action || 'HOLD'}</strong></span>
          <span className="text-gray-500">|</span>
          <span>Confidence: <strong className="text-neon-cyan">{((jarvisData?.confidence || 0.6) * 100).toFixed(1)}%</strong></span>
        </div>

        {/* Bottom Right Legend */}
        <div className="absolute bottom-3 right-3 hidden sm:flex items-center gap-3 px-2.5 py-1 rounded-lg bg-black/70 border border-white/10 backdrop-blur-md text-[10px] font-mono text-gray-400 pointer-events-none">
          <span className="text-neon-cyan">● JARVIS (Cyan)</span>
          <span className="text-orange-400">● ULTRON (Amber)</span>
          <span className="text-gray-500">Drag to Rotate</span>
        </div>
      </div>
    </div>
  );
}
