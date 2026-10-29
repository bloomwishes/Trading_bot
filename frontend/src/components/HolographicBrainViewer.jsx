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
  Layers,
  Sparkles,
  Cpu,
  Info,
} from 'lucide-react';

/**
 * HOLOGRAPHIC 3D NEURAL BRAIN VIEWER (AVENGERS JARVIS & ULTRON ENGINE)
 *
 * Implements a 60 FPS 3D perspective holographic canvas rendering:
 * 1. JARVIS (Left): Cyan / Ice Blue coherent neural consciousness sphere.
 * 2. ULTRON (Right): Fiery Amber / Radiant Orange fractured dynamic neural matrix.
 * 3. Central Synaptic Bridge: Inter-brain neural pathways exchanging action potentials.
 * 4. Realistic Neuron Firing: Action potential energy packets traveling along axons,
 *    node somatic flash halos, expanding shockwave rings, and dendritic lightning sparks.
 * 5. Full 3D rotation, zoom, interactive node inspection HUD, and sound synthesis.
 */

// Math helpers
const DEG2RAD = Math.PI / 180;

function createFibonacciSphere(numPoints, radius) {
  const points = [];
  const phi = Math.PI * (3 - Math.sqrt(5)); // golden angle in radians

  for (let i = 0; i < numPoints; i++) {
    const y = 1 - (i / (numPoints - 1 || 1)) * 2; // y goes from 1 to -1
    const radiusAtY = Math.sqrt(Math.max(0, 1 - y * y)); // radius at y
    const theta = phi * i; // golden angle increment

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
  const [firingSpeed, setFiringSpeed] = useState(1.0); // 0.5 (calm) | 1.0 (normal) | 2.0 (warp)
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [activeTelemetry, setActiveTelemetry] = useState({
    fps: 60,
    activePulses: 0,
    firingRate: '1,420 Hz',
    coherence: '98.6%',
  });

  // 3D Camera & Interaction state
  const cameraRef = useRef({
    rotX: 12 * DEG2RAD,
    rotY: -20 * DEG2RAD,
    targetRotX: 12 * DEG2RAD,
    targetRotY: -20 * DEG2RAD,
    zoom: 1.0,
    targetZoom: 1.0,
    isDragging: false,
    lastMouseX: 0,
    lastMouseY: 0,
    autoRotSpeed: 0.0035,
  });

  // Simulation Data Graph Ref
  const sceneRef = useRef({
    jarvisNodes: [],
    jarvisAxons: [],
    jarvisPulses: [],
    ultronNodes: [],
    ultronAxons: [],
    ultronPulses: [],
    bridgeAxons: [],
    bridgePulses: [],
    sparks: [],
    shockwaves: [],
    lastSurgeTime: 0,
    pulseIdCounter: 0,
  });

  // Sound Synthesizer via Web Audio API
  const playSynapticTone = useCallback((freq = 520, duration = 0.08, type = 'sine') => {
    if (!soundEnabled) return;
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(freq * 1.5, ctx.currentTime + duration);

      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch {
      // AudioContext muted or blocked
    }
  }, [soundEnabled]);

  // Build 3D Neural Nodes and Axons graph
  const initSceneGraph = useCallback(() => {
    const scene = sceneRef.current;
    scene.jarvisNodes = [];
    scene.jarvisAxons = [];
    scene.jarvisPulses = [];
    scene.ultronNodes = [];
    scene.ultronAxons = [];
    scene.ultronPulses = [];
    scene.bridgeAxons = [];
    scene.bridgePulses = [];

    // Helper to generate a brain entity
    const buildBrainEntity = (isUltron = false) => {
      const nodes = [];
      const axons = [];
      const colorTheme = isUltron ? 'amber' : 'cyan';

      // 1. INPUT LAYER (16 sensory cortex nodes on outer coronal ring)
      const inputCoords = [];
      const numInputs = 16;
      for (let i = 0; i < numInputs; i++) {
        const theta = (i / numInputs) * Math.PI * 2;
        const r = 165;
        const tilt = Math.sin(i * 1.5) * 20;
        inputCoords.push({
          x: Math.cos(theta) * r,
          y: Math.sin(theta) * r + tilt,
          z: Math.sin(theta * 2) * 45,
        });
      }

      inputCoords.forEach((pt, idx) => {
        nodes.push({
          id: `${colorTheme}_in_${idx}`,
          layer: 'input',
          index: idx,
          name: `INDICATOR_${idx + 1}`,
          x: pt.x,
          y: pt.y,
          z: pt.z,
          baseRadius: 3.8,
          currentRadius: 3.8,
          activation: 0.3 + (idx % 5) * 0.12,
          flash: 0,
          theme: colorTheme,
          shockwaves: [],
        });
      });

      // 2. LAYER 1: HIDDEN CORTEX (64 nodes on middle sphere)
      const l1Radius = isUltron ? 125 : 120;
      const l1Coords = createFibonacciSphere(64, l1Radius);
      l1Coords.forEach((pt, idx) => {
        // Ultron gets slightly more irregular/fractured jitter
        const jitter = isUltron ? (Math.sin(idx * 7) * 8) : 0;
        nodes.push({
          id: `${colorTheme}_l1_${idx}`,
          layer: 'l1',
          index: idx,
          name: `NEURON_L1_${idx}`,
          x: pt.x + jitter,
          y: pt.y - jitter * 0.5,
          z: pt.z + jitter * 0.7,
          baseRadius: 3.0,
          currentRadius: 3.0,
          activation: 0.2 + (idx % 7) * 0.1,
          flash: 0,
          theme: colorTheme,
          shockwaves: [],
        });
      });

      // 3. LAYER 2: SYNTHESIS CORE (32 nodes on inner dense sphere)
      const l2Radius = isUltron ? 75 : 70;
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
          baseRadius: 3.4,
          currentRadius: 3.4,
          activation: 0.35 + (idx % 4) * 0.15,
          flash: 0,
          theme: colorTheme,
          shockwaves: [],
        });
      });

      // 4. LAYER 3: DECISION NUCLEUS (3 core output nodes: BUY, HOLD, SELL)
      const outputConfigs = [
        { name: 'DECISION: BUY', offset: { x: -28, y: -15, z: 0 }, actKey: 'BUY' },
        { name: 'DECISION: HOLD', offset: { x: 0, y: 25, z: 10 }, actKey: 'HOLD' },
        { name: 'DECISION: SELL', offset: { x: 28, y: -15, z: 0 }, actKey: 'SELL' },
      ];
      outputConfigs.forEach((cfg, idx) => {
        nodes.push({
          id: `${colorTheme}_out_${idx}`,
          layer: 'output',
          index: idx,
          name: cfg.name,
          x: cfg.offset.x,
          y: cfg.offset.y,
          z: cfg.offset.z,
          baseRadius: 6.0,
          currentRadius: 6.0,
          activation: 0.5,
          flash: 0,
          theme: colorTheme,
          shockwaves: [],
        });
      });

      // 5. AXONS: CONNECT LAYERS
      // Inputs -> L1 connections (connect each input to 3-5 nearby L1 neurons)
      for (let i = 0; i < 16; i++) {
        for (let j = 0; j < 64; j++) {
          if ((i * 4 + j) % 7 === 0 || (i + j) % 11 === 0) {
            axons.push({
              source: `${colorTheme}_in_${i}`,
              target: `${colorTheme}_l1_${j}`,
              weight: 0.4 + ((i * j) % 10) * 0.06,
              theme: colorTheme,
            });
          }
        }
      }

      // L1 -> L2 connections
      for (let i = 0; i < 64; i++) {
        for (let j = 0; j < 32; j++) {
          if ((i + j * 2) % 6 === 0 || (i * 3 + j) % 13 === 0) {
            axons.push({
              source: `${colorTheme}_l1_${i}`,
              target: `${colorTheme}_l2_${j}`,
              weight: 0.5 + ((i + j) % 8) * 0.06,
              theme: colorTheme,
            });
          }
        }
      }

      // L2 -> Output nucleus
      for (let i = 0; i < 32; i++) {
        const outTarget = i % 3;
        axons.push({
          source: `${colorTheme}_l2_${i}`,
          target: `${colorTheme}_out_${outTarget}`,
          weight: 0.7 + (i % 5) * 0.06,
          theme: colorTheme,
        });
      }

      // Intra-layer lateral synapses (adds geodesic neural web density)
      const numLateral = isUltron ? 45 : 35;
      for (let k = 0; k < numLateral; k++) {
        const srcIdx = (k * 7) % 64;
        const tgtIdx = (k * 13 + 3) % 64;
        if (srcIdx !== tgtIdx) {
          axons.push({
            source: `${colorTheme}_l1_${srcIdx}`,
            target: `${colorTheme}_l1_${tgtIdx}`,
            weight: 0.35,
            theme: colorTheme,
            isLateral: true,
          });
        }
      }

      return { nodes, axons };
    };

    const jarvis = buildBrainEntity(false);
    scene.jarvisNodes = jarvis.nodes;
    scene.jarvisAxons = jarvis.axons;

    const ultron = buildBrainEntity(true);
    scene.ultronNodes = ultron.nodes;
    scene.ultronAxons = ultron.axons;

    // Build Central Synaptic Bridge (Corpus Callosum bridging Jarvis and Ultron)
    for (let b = 0; b < 12; b++) {
      const jNode = scene.jarvisNodes.find(
        (n) => n.layer === 'l1' && n.index === (b * 5 + 2) % 64
      );
      const uNode = scene.ultronNodes.find(
        (n) => n.layer === 'l1' && n.index === (b * 5 + 7) % 64
      );
      if (jNode && uNode) {
        scene.bridgeAxons.push({
          source: jNode.id,
          target: uNode.id,
          weight: 0.75,
          theme: 'bridge',
        });
      }
    }
  }, []);

  // Update node activations from live props
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene.jarvisNodes.length) {
      initSceneGraph();
    }

    // Apply Jarvis Live Activations
    const jInputs = jarvisData?.input_features || [];
    const jL1 = jarvisData?.layer1_activations || [];
    const jL2 = jarvisData?.layer2_activations || [];
    const jProbs = jarvisData?.probabilities || { BUY: 0.33, HOLD: 0.34, SELL: 0.33 };

    scene.jarvisNodes.forEach((node) => {
      if (node.layer === 'input' && jInputs[node.index]) {
        const feat = jInputs[node.index];
        node.name = feat.name || node.name;
        node.activation = Math.min(1.0, Math.max(0.1, Math.abs(feat.norm_value ?? 0.5)));
      } else if (node.layer === 'l1' && jL1[node.index] !== undefined) {
        node.activation = Math.min(1.0, Math.max(0.08, jL1[node.index]));
      } else if (node.layer === 'l2' && jL2[node.index] !== undefined) {
        node.activation = Math.min(1.0, Math.max(0.1, jL2[node.index]));
      } else if (node.layer === 'output') {
        const k = node.index === 0 ? 'BUY' : node.index === 1 ? 'HOLD' : 'SELL';
        node.activation = jProbs[k] || 0.33;
      }
    });

    // Apply Ultron Live Activations (from ultronData or alternative model)
    const uInputs = ultronData?.input_features || jInputs;
    const uL1 = ultronData?.layer1_activations || jL1;
    const uL2 = ultronData?.layer2_activations || jL2;
    const uProbs = ultronData?.probabilities || jProbs;

    scene.ultronNodes.forEach((node) => {
      if (node.layer === 'input' && uInputs[node.index]) {
        const feat = uInputs[node.index];
        node.name = feat.name || node.name;
        node.activation = Math.min(1.0, Math.max(0.1, Math.abs(feat.norm_value ?? 0.5)));
      } else if (node.layer === 'l1' && uL1[node.index] !== undefined) {
        // Ultron has higher baseline excitement
        node.activation = Math.min(1.0, Math.max(0.12, uL1[node.index] * 1.05));
      } else if (node.layer === 'l2' && uL2[node.index] !== undefined) {
        node.activation = Math.min(1.0, Math.max(0.15, uL2[node.index] * 1.05));
      } else if (node.layer === 'output') {
        const k = node.index === 0 ? 'BUY' : node.index === 1 ? 'HOLD' : 'SELL';
        node.activation = uProbs[k] || 0.33;
      }
    });
  }, [jarvisData, ultronData, initSceneGraph]);

  // Handle Synaptic Surge / Manual pulse triggering
  const triggerSynapticSurge = useCallback(() => {
    const scene = sceneRef.current;
    scene.lastSurgeTime = Date.now();
    playSynapticTone(660, 0.22, 'triangle');

    // Ignite all inputs on both brains and send pulses cascading down
    const igniteEntity = (nodes, axons, pulses, theme) => {
      nodes.forEach((n) => {
        if (n.layer === 'input') {
          n.flash = 1.0;
          n.shockwaves.push({ r: 4, maxR: 28, alpha: 1.0, color: theme === 'amber' ? '#ff9900' : '#00f0ff' });
        }
      });

      // Spawn pulses along all input -> L1 axons
      axons.forEach((axon) => {
        if (axon.source.includes('_in_')) {
          pulses.push({
            id: ++scene.pulseIdCounter,
            source: axon.source,
            target: axon.target,
            progress: 0.0,
            speed: 0.035 * firingSpeed,
            size: 4.0,
            theme: axon.theme,
            isBridge: false,
          });
        }
      });
    };

    igniteEntity(scene.jarvisNodes, scene.jarvisAxons, scene.jarvisPulses, 'cyan');
    igniteEntity(scene.ultronNodes, scene.ultronAxons, scene.ultronPulses, 'amber');

    // Spawn 10 cross-bridge pulses
    scene.bridgeAxons.forEach((axon) => {
      scene.bridgePulses.push({
        id: ++scene.pulseIdCounter,
        source: Math.random() > 0.5 ? axon.source : axon.target,
        target: Math.random() > 0.5 ? axon.target : axon.source,
        progress: 0.0,
        speed: 0.022 * firingSpeed,
        size: 4.5,
        theme: 'bridge',
        isBridge: true,
      });
    });

    onTriggerSurge();
  }, [firingSpeed, playSynapticTone, onTriggerSurge]);

  // React to external surge prop
  useEffect(() => {
    if (isSurgeFiring) {
      triggerSynapticSurge();
    }
  }, [isSurgeFiring, triggerSynapticSurge]);

  // Mouse & Touch Interaction Handlers
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
      // Clamp pitch to avoid gimbal flip
      cam.targetRotX = Math.max(-Math.PI * 0.45, Math.min(Math.PI * 0.45, cam.targetRotX));
      cam.lastMouseX = e.clientX;
      cam.lastMouseY = e.clientY;
    }

    // Raycast / Proximity check for node hover tooltip
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let closest = null;
    let minDist = 18; // hover capture radius

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
    cam.targetZoom = Math.max(0.65, Math.min(1.85, cam.targetZoom + delta));
  };

  const resetCamera = () => {
    const cam = cameraRef.current;
    cam.targetRotX = 12 * DEG2RAD;
    cam.targetRotY = -20 * DEG2RAD;
    cam.targetZoom = 1.0;
  };

  // Main Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    initSceneGraph();

    let frameCount = 0;
    let lastFpsTime = performance.now();
    let currentFps = 60;

    const render = () => {
      const scene = sceneRef.current;
      const cam = cameraRef.current;

      // Handle Canvas DPI Sizing
      const container = containerRef.current;
      if (container) {
        const width = container.clientWidth;
        const height = isFullscreen ? window.innerHeight - 80 : 640;
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

      // Smooth camera interpolation
      cam.rotX += (cam.targetRotX - cam.rotX) * 0.1;
      cam.rotY += (cam.targetRotY - cam.rotY) * 0.1;
      cam.zoom += (cam.targetZoom - cam.zoom) * 0.1;

      // Auto-rotation when not dragging
      if (autoRotate && !cam.isDragging) {
        cam.targetRotY += cam.autoRotSpeed * firingSpeed;
      }

      // Background Clear with Sci-Fi Dark Cyber Gradient
      ctx.fillStyle = '#05070d';
      ctx.fillRect(0, 0, screenW, screenH);

      // Draw subtle holographic backdrop grid & radial glow
      const bgGrad = ctx.createRadialGradient(centerX, centerY, 80, centerX, centerY, screenW * 0.7);
      bgGrad.addColorStop(0, 'rgba(0, 240, 255, 0.04)');
      bgGrad.addColorStop(0.5, 'rgba(255, 120, 0, 0.025)');
      bgGrad.addColorStop(1, 'rgba(5, 7, 13, 0)');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, screenW, screenH);

      // Draw Iron Man / Stark Tech HUD rings & reticles
      ctx.save();
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.08)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 280 * cam.zoom, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = 'rgba(255, 120, 0, 0.06)';
      ctx.beginPath();
      ctx.arc(centerX, centerY, 340 * cam.zoom, 0, Math.PI * 2);
      ctx.stroke();

      // Rotating HUD tick marks
      const hudAngle = frameCount * 0.005;
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.2)';
      for (let a = 0; a < 8; a++) {
        const ang = hudAngle + (a * Math.PI) / 4;
        const r1 = 275 * cam.zoom;
        const r2 = 285 * cam.zoom;
        ctx.beginPath();
        ctx.moveTo(centerX + Math.cos(ang) * r1, centerY + Math.sin(ang) * r1);
        ctx.lineTo(centerX + Math.cos(ang) * r2, centerY + Math.sin(ang) * r2);
        ctx.stroke();
      }
      ctx.restore();

      // 3D Projection Math (Responsive to screen width)
      const responsiveFocal = Math.min(620, Math.max(380, screenW * 0.85));
      const focalLength = responsiveFocal * cam.zoom;
      const cameraDistance = 700;

      const cosY = Math.cos(cam.rotY);
      const sinY = Math.sin(cam.rotY);
      const cosX = Math.cos(cam.rotX);
      const sinX = Math.sin(cam.rotX);

      // Determine entity offsets based on viewMode (Responsive spacing)
      const baseOffset = Math.min(235, Math.max(120, screenW * 0.26));
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

      // Project a 3D point (world coords) to 2D screen coords
      const projectPoint = (x, y, z, offsetX = 0) => {
        const wx = x + offsetX;
        const wy = y;
        const wz = z;

        // Yaw (rotY) around origin
        const x1 = wx * cosY + wz * sinY;
        const z1 = -wx * sinY + wz * cosY;

        // Pitch (rotX)
        const y2 = wy * cosX - z1 * sinX;
        const z2 = wy * sinX + z1 * cosX;

        // Perspective division
        const depth = z2 + cameraDistance;
        const scale = depth > 10 ? focalLength / depth : 0;
        const screenX = centerX + x1 * scale;
        const screenY = centerY + y2 * scale;

        return {
          sx: screenX,
          sy: screenY,
          depth: z2,
          scale,
        };
      };

      // Node lookup map
      const nodeMap = new Map();

      // Update and Project Jarvis Nodes
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

      // Update and Project Ultron Nodes
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

      // Continuous Organic Firing Simulation (spawns micro-pulses based on real activation values)
      const simulateOrganicFiring = (nodes, axons, pulses, theme) => {
        if (Math.random() < 0.22 * firingSpeed) {
          // Pick a random active node to fire
          const activeNodes = nodes.filter((n) => n.activation > 0.35);
          if (activeNodes.length > 0) {
            const firingNode = activeNodes[Math.floor(Math.random() * activeNodes.length)];
            firingNode.flash = Math.min(1.0, firingNode.flash + 0.6);

            // Find outgoing axons
            const outgoing = axons.filter((a) => a.source === firingNode.id);
            if (outgoing.length > 0) {
              const axon = outgoing[Math.floor(Math.random() * outgoing.length)];
              pulses.push({
                id: ++scene.pulseIdCounter,
                source: axon.source,
                target: axon.target,
                progress: 0.0,
                speed: (0.018 + axon.weight * 0.02) * firingSpeed,
                size: 2.5 + axon.weight * 1.5,
                theme: axon.theme,
                isBridge: false,
              });
            }
          }
        }
      };

      if (renderJarvis) simulateOrganicFiring(scene.jarvisNodes, scene.jarvisAxons, scene.jarvisPulses, 'cyan');
      if (renderUltron) simulateOrganicFiring(scene.ultronNodes, scene.ultronAxons, scene.ultronPulses, 'amber');

      // Bridge organic firing (in dual mode)
      if (viewMode === 'dual' && scene.bridgeAxons.length > 0 && Math.random() < 0.12 * firingSpeed) {
        const bridgeAxon = scene.bridgeAxons[Math.floor(Math.random() * scene.bridgeAxons.length)];
        const fromJarvis = Math.random() > 0.5;
        scene.bridgePulses.push({
          id: ++scene.pulseIdCounter,
          source: fromJarvis ? bridgeAxon.source : bridgeAxon.target,
          target: fromJarvis ? bridgeAxon.target : bridgeAxon.source,
          progress: 0.0,
          speed: 0.016 * firingSpeed,
          size: 3.5,
          theme: 'bridge',
          isBridge: true,
        });
      }

      // DRAWING PIPELINE: Enable Additive Blending for true glowing holograms!
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      // 1. DRAW VOLUMETRIC CORES (Jarvis Core & Ultron Core)
      const drawCoreGlow = (offsetX, theme) => {
        const coreProj = projectPoint(0, 0, 0, offsetX);
        if (coreProj.scale <= 0) return;

        const coreRadius = (theme === 'amber' ? 65 : 60) * coreProj.scale;
        const grad = ctx.createRadialGradient(
          coreProj.sx,
          coreProj.sy,
          4,
          coreProj.sx,
          coreProj.sy,
          coreRadius * 2.2
        );

        if (theme === 'amber') {
          // Ultron Core: Fiery Molten Radiance
          grad.addColorStop(0, 'rgba(255, 240, 200, 0.9)');
          grad.addColorStop(0.2, 'rgba(255, 140, 0, 0.6)');
          grad.addColorStop(0.5, 'rgba(255, 60, 0, 0.25)');
          grad.addColorStop(1, 'rgba(255, 20, 0, 0)');
        } else {
          // Jarvis Core: Coherent Electric Blue / Cyan Radiance
          grad.addColorStop(0, 'rgba(230, 255, 255, 0.95)');
          grad.addColorStop(0.25, 'rgba(0, 240, 255, 0.6)');
          grad.addColorStop(0.55, 'rgba(0, 119, 255, 0.22)');
          grad.addColorStop(1, 'rgba(0, 50, 180, 0)');
        }

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(coreProj.sx, coreProj.sy, coreRadius * 2.2, 0, Math.PI * 2);
        ctx.fill();

        // Orbital ring filaments around nucleus
        const numRings = theme === 'amber' ? 4 : 5;
        for (let r = 0; r < numRings; r++) {
          const ringRad = (25 + r * 14) * coreProj.scale;
          const tiltX = (frameCount * 0.01 * (r % 2 === 0 ? 1 : -1)) + r;
          ctx.strokeStyle =
            theme === 'amber'
              ? `rgba(255, 160, 20, ${0.15 + r * 0.05})`
              : `rgba(0, 240, 255, ${0.18 + r * 0.05})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.ellipse(coreProj.sx, coreProj.sy, ringRad, ringRad * 0.45, tiltX, 0, Math.PI * 2);
          ctx.stroke();
        }
      };

      if (renderJarvis) drawCoreGlow(jarvisOffsetX, 'cyan');
      if (renderUltron) drawCoreGlow(ultronOffsetX, 'amber');

      // 2. DRAW AXONS (Synaptic Fibers)
      const drawAxonList = (axons) => {
        axons.forEach((axon) => {
          const sNode = nodeMap.get(axon.source);
          const tNode = nodeMap.get(axon.target);
          if (!sNode || !tNode || sNode.scale <= 0 || tNode.scale <= 0) return;

          const avgDepth = (sNode.projZ + tNode.projZ) / 2;
          const depthAlpha = Math.max(0.08, Math.min(0.85, (avgDepth + 300) / 600));
          const baseAlpha = axon.weight * 0.45 * depthAlpha;

          ctx.lineWidth = (axon.isLateral ? 0.7 : 1.2) * sNode.scale;

          if (axon.theme === 'bridge') {
            // Bridge Axon: Vibrant Cyan-to-Amber gradient
            const bridgeGrad = ctx.createLinearGradient(
              sNode.projX,
              sNode.projY,
              tNode.projX,
              tNode.projY
            );
            bridgeGrad.addColorStop(0, `rgba(0, 240, 255, ${baseAlpha * 1.5})`);
            bridgeGrad.addColorStop(0.5, `rgba(255, 0, 229, ${baseAlpha * 1.8})`);
            bridgeGrad.addColorStop(1, `rgba(255, 140, 0, ${baseAlpha * 1.5})`);
            ctx.strokeStyle = bridgeGrad;
          } else if (axon.theme === 'amber') {
            ctx.strokeStyle = `rgba(255, 120, 10, ${baseAlpha})`;
          } else {
            ctx.strokeStyle = `rgba(0, 200, 255, ${baseAlpha})`;
          }

          ctx.beginPath();
          ctx.moveTo(sNode.projX, sNode.projY);
          ctx.lineTo(tNode.projX, tNode.projY);
          ctx.stroke();
        });
      };

      if (renderJarvis) drawAxonList(scene.jarvisAxons);
      if (renderUltron) drawAxonList(scene.ultronAxons);
      if (viewMode === 'dual') drawAxonList(scene.bridgeAxons);

      // 3. UPDATE & DRAW ACTION POTENTIALS (Firing Energy Pulses)
      const updateAndDrawPulses = (pulses) => {
        for (let i = pulses.length - 1; i >= 0; i--) {
          const pulse = pulses[i];
          pulse.progress += pulse.speed;

          const sNode = nodeMap.get(pulse.source);
          const tNode = nodeMap.get(pulse.target);

          if (!sNode || !tNode || pulse.progress >= 1.0) {
            // Pulse reached target neuron! Trigger somatic flash & shockwave
            if (tNode) {
              tNode.flash = 1.0;
              tNode.shockwaves.push({
                r: 3,
                maxR: (tNode.layer === 'output' ? 38 : 18) * tNode.scale,
                alpha: 1.0,
                color: tNode.theme === 'amber' ? '#ffaa00' : '#00f0ff',
              });

              // Downstream cascade: with 35% probability, trigger next-layer pulse
              if (Math.random() < 0.38) {
                const isUltron = tNode.theme === 'amber';
                const axons = isUltron ? scene.ultronAxons : scene.jarvisAxons;
                const nextAxons = axons.filter((a) => a.source === tNode.id);
                if (nextAxons.length > 0) {
                  const nextAxon = nextAxons[Math.floor(Math.random() * nextAxons.length)];
                  pulses.push({
                    id: ++scene.pulseIdCounter,
                    source: nextAxon.source,
                    target: nextAxon.target,
                    progress: 0.0,
                    speed: (0.025 + nextAxon.weight * 0.02) * firingSpeed,
                    size: 3.2,
                    theme: nextAxon.theme,
                    isBridge: false,
                  });
                }
              }
            }
            pulses.splice(i, 1);
            continue;
          }

          // Interpolate 2D position along axon with smooth easing
          const px = sNode.projX + (tNode.projX - sNode.projX) * pulse.progress;
          const py = sNode.projY + (tNode.projY - sNode.projY) * pulse.progress;
          const pScale = (sNode.scale + tNode.scale) / 2;
          const pRadius = pulse.size * pScale;

          // Action Potential Glow
          const pGrad = ctx.createRadialGradient(px, py, 1, px, py, pRadius * 3);
          if (pulse.theme === 'bridge') {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.3, 'rgba(255, 0, 229, 0.9)');
            pGrad.addColorStop(1, 'rgba(0, 240, 255, 0)');
          } else if (pulse.theme === 'amber') {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.3, 'rgba(255, 170, 0, 0.95)');
            pGrad.addColorStop(1, 'rgba(255, 60, 0, 0)');
          } else {
            pGrad.addColorStop(0, '#ffffff');
            pGrad.addColorStop(0.3, 'rgba(0, 240, 255, 0.95)');
            pGrad.addColorStop(1, 'rgba(0, 100, 255, 0)');
          }

          ctx.fillStyle = pGrad;
          ctx.beginPath();
          ctx.arc(px, py, pRadius * 3, 0, Math.PI * 2);
          ctx.fill();

          // Action Potential Solid Photon Center
          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(px, py, pRadius * 0.9, 0, Math.PI * 2);
          ctx.fill();
        }
      };

      if (renderJarvis) updateAndDrawPulses(scene.jarvisPulses);
      if (renderUltron) updateAndDrawPulses(scene.ultronPulses);
      if (viewMode === 'dual') updateAndDrawPulses(scene.bridgePulses);

      // 4. DRAW NEURONS (Somatic Nodes & Shockwaves)
      const drawNodesList = (nodes) => {
        // Sort by Z depth so foreground nodes draw over background ones
        const sorted = [...nodes].sort((a, b) => b.projZ - a.projZ);

        sorted.forEach((node) => {
          if (node.scale <= 0) return;

          // Decay somatic flash & pulse radius
          node.flash *= 0.92;
          const isHighAct = node.activation > 0.65;
          const flashBoost = node.flash * 4.0;
          const targetRad = (node.baseRadius + node.activation * 2.5 + flashBoost) * node.scale;
          node.currentRadius = targetRad;

          const isHovered = hoveredNode && hoveredNode.id === node.id;
          const isAmber = node.theme === 'amber';

          // Node Shockwaves (Ripple halos)
          for (let w = node.shockwaves.length - 1; w >= 0; w--) {
            const sw = node.shockwaves[w];
            sw.r += 0.8 * firingSpeed;
            sw.alpha *= 0.92;
            if (sw.alpha < 0.05 || sw.r >= sw.maxR) {
              node.shockwaves.splice(w, 1);
              continue;
            }
            ctx.strokeStyle = sw.color.replace(')', `, ${sw.alpha})`).replace('rgb', 'rgba');
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(node.projX, node.projY, sw.r, 0, Math.PI * 2);
            ctx.stroke();
          }

          // Node Outer Glow Aura
          const glowRad = Math.max(8, node.currentRadius * (isHighAct ? 3.5 : 2.2));
          const nodeGrad = ctx.createRadialGradient(
            node.projX,
            node.projY,
            node.currentRadius * 0.3,
            node.projX,
            node.projY,
            glowRad
          );

          if (isAmber) {
            nodeGrad.addColorStop(
              0,
              isHighAct || node.flash > 0.3 ? 'rgba(255, 255, 220, 1)' : 'rgba(255, 180, 40, 0.9)'
            );
            nodeGrad.addColorStop(0.4, 'rgba(255, 120, 0, 0.6)');
            nodeGrad.addColorStop(1, 'rgba(255, 50, 0, 0)');
          } else {
            nodeGrad.addColorStop(
              0,
              isHighAct || node.flash > 0.3 ? 'rgba(240, 255, 255, 1)' : 'rgba(0, 240, 255, 0.9)'
            );
            nodeGrad.addColorStop(0.4, 'rgba(0, 160, 255, 0.6)');
            nodeGrad.addColorStop(1, 'rgba(0, 80, 255, 0)');
          }

          ctx.fillStyle = nodeGrad;
          ctx.beginPath();
          ctx.arc(node.projX, node.projY, glowRad, 0, Math.PI * 2);
          ctx.fill();

          // Node Solid Core
          ctx.fillStyle = isHighAct || node.flash > 0.3 ? '#ffffff' : (isAmber ? '#ffcc44' : '#66ffff');
          ctx.beginPath();
          ctx.arc(node.projX, node.projY, Math.max(1.5, node.currentRadius * 0.6), 0, Math.PI * 2);
          ctx.fill();

          // Hover Target Reticle
          if (isHovered) {
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            const reticleSize = node.currentRadius * 2.5 + 4;
            ctx.strokeRect(
              node.projX - reticleSize / 2,
              node.projY - reticleSize / 2,
              reticleSize,
              reticleSize
            );
          }
        });
      };

      if (renderJarvis) drawNodesList(scene.jarvisNodes);
      if (renderUltron) drawNodesList(scene.ultronNodes);

      // 4.5 DRAW CINEMATIC LIGHTNING ARCS (Avengers Movie Neural Discharges)
      if (Math.random() < 0.42 * firingSpeed) {
        const pool = [];
        if (renderJarvis) pool.push(...scene.jarvisNodes.filter((n) => n.activation > 0.45 && n.scale > 0));
        if (renderUltron) pool.push(...scene.ultronNodes.filter((n) => n.activation > 0.45 && n.scale > 0));

        if (pool.length >= 2) {
          const n1 = pool[Math.floor(Math.random() * pool.length)];
          const n2 = pool[Math.floor(Math.random() * pool.length)];
          const dist = Math.hypot(n1.projX - n2.projX, n1.projY - n2.projY);

          if (n1.id !== n2.id && dist < 160 && dist > 20) {
            ctx.save();
            ctx.strokeStyle =
              n1.theme === 'amber' || n2.theme === 'amber'
                ? 'rgba(255, 190, 60, 0.85)'
                : 'rgba(160, 245, 255, 0.9)';
            ctx.lineWidth = 1.3;
            ctx.beginPath();
            ctx.moveTo(n1.projX, n1.projY);
            // 2-step jagged lightning zigzag
            const midX = (n1.projX + n2.projX) / 2 + (Math.random() - 0.5) * 22;
            const midY = (n1.projY + n2.projY) / 2 + (Math.random() - 0.5) * 22;
            ctx.lineTo(midX, midY);
            ctx.lineTo(n2.projX, n2.projY);
            ctx.stroke();
            ctx.restore();
          }
        }
      }

      ctx.restore(); // Restore globalCompositeOperation

      // 5. DRAW HOLOGRAPHIC HUD CALLOUT FOR HOVERED NODE
      if (hoveredNode && hoveredNode.projX !== undefined) {
        ctx.save();
        const hn = hoveredNode;
        const boxX = hn.projX + 25;
        const boxY = hn.projY - 45;
        const boxW = 195;
        const boxH = 75;

        // Callout diagonal line
        ctx.strokeStyle = hn.theme === 'amber' ? '#ff9900' : '#00f0ff';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hn.projX, hn.projY);
        ctx.lineTo(hn.projX + 15, hn.projY - 15);
        ctx.lineTo(boxX, boxY + boxH / 2);
        ctx.stroke();

        // Data card background
        ctx.fillStyle = 'rgba(10, 15, 26, 0.92)';
        ctx.strokeStyle = hn.theme === 'amber' ? 'rgba(255, 140, 0, 0.5)' : 'rgba(0, 240, 255, 0.5)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(boxX, boxY, boxW, boxH, 6);
        ctx.fill();
        ctx.stroke();

        // Data card text
        ctx.fillStyle = hn.theme === 'amber' ? '#ffaa00' : '#00f0ff';
        ctx.font = 'bold 10px monospace';
        ctx.fillText(
          `${hn.theme.toUpperCase()}: ${hn.layer.toUpperCase()} NODE`,
          boxX + 10,
          boxY + 18
        );

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 11px sans-serif';
        ctx.fillText(hn.name, boxX + 10, boxY + 36);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px monospace';
        ctx.fillText(
          `Activation: ${(hn.activation * 100).toFixed(1)}% | Voltage: High`,
          boxX + 10,
          boxY + 52
        );

        ctx.fillStyle = hn.activation > 0.6 ? '#00ff88' : '#e2e8f0';
        ctx.fillText(
          hn.activation > 0.6 ? '● SYNAPSE EXCITATORY (ACTIVE)' : '○ SYNAPSE RESTING',
          boxX + 10,
          boxY + 66
        );

        ctx.restore();
      }

      // 6. UPDATE TELEMETRY STATS (Every 30 frames)
      frameCount++;
      if (frameCount % 30 === 0) {
        const now = performance.now();
        const delta = (now - lastFpsTime) / 1000;
        currentFps = Math.round(30 / delta);
        lastFpsTime = now;

        const totalPulses =
          scene.jarvisPulses.length + scene.ultronPulses.length + scene.bridgePulses.length;

        setActiveTelemetry({
          fps: Math.min(60, currentFps),
          activePulses: totalPulses,
          firingRate: `${Math.round(1200 + totalPulses * 24)} Hz`,
          coherence: `${(98.2 + Math.random() * 1.5).toFixed(1)}%`,
        });
      }

      animFrameRef.current = requestAnimationFrame(render);
    };

    animFrameRef.current = requestAnimationFrame(render);

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [
    viewMode,
    autoRotate,
    firingSpeed,
    isFullscreen,
    hoveredNode,
    initSceneGraph,
  ]);

  return (
    <div
      ref={containerRef}
      className={`glass-card relative overflow-hidden border border-neon-cyan/40 shadow-[0_0_40px_rgba(0,240,255,0.12)] transition-all ${
        isFullscreen ? 'fixed inset-4 z-50 bg-[#05070d]/95' : 'w-full'
      }`}
    >
      {/* Top Holographic Header Bar */}
      <div className="flex flex-wrap items-center justify-between p-4 border-b border-gray-800/80 bg-black/40 backdrop-blur-md gap-3">
        {/* Left: Consciousness State Badges */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyber-surface/90 border border-neon-cyan/30">
            <span className="w-2.5 h-2.5 rounded-full bg-neon-cyan animate-ping" />
            <span className="text-xs font-bold font-mono tracking-wider text-neon-cyan uppercase">
              JARVIS SYNAPTIC ENGINE
            </span>
            <span className="text-[10px] text-gray-400 font-mono">Macro & Defensive</span>
          </div>

          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyber-surface/90 border border-orange-500/30">
            <span className="w-2.5 h-2.5 rounded-full bg-orange-400 animate-pulse" />
            <span className="text-xs font-bold font-mono tracking-wider text-orange-400 uppercase">
              ULTRON NEURAL MATRIX
            </span>
            <span className="text-[10px] text-gray-400 font-mono">Dynamic Volatility</span>
          </div>
        </div>

        {/* Center: View Switcher (Dual vs Jarvis vs Ultron) */}
        <div className="flex items-center p-1 rounded-xl bg-cyber-bg/90 border border-gray-800">
          <button
            onClick={() => setViewMode('dual')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
              viewMode === 'dual'
                ? 'bg-gradient-to-r from-neon-cyan/30 via-purple-500/20 to-orange-500/30 text-white border border-white/20 shadow-lg'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Sparkles size={13} className="text-neon-cyan" />
            <span>Avengers Convergence (Dual)</span>
          </button>
          <button
            onClick={() => setViewMode('jarvis')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
              viewMode === 'jarvis'
                ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40 shadow-[0_0_12px_rgba(0,240,255,0.3)]'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Cpu size={13} />
            <span>JARVIS Core</span>
          </button>
          <button
            onClick={() => setViewMode('ultron')}
            className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
              viewMode === 'ultron'
                ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40 shadow-[0_0_12px_rgba(255,140,0,0.3)]'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Zap size={13} />
            <span>ULTRON Matrix</span>
          </button>
        </div>

        {/* Right: Quick Controls */}
        <div className="flex items-center gap-2">
          {/* Synaptic Surge Button */}
          <button
            onClick={triggerSynapticSurge}
            className="px-3 py-1.5 rounded-lg text-xs font-bold font-mono bg-gradient-to-r from-neon-cyan to-neon-magenta text-black hover:opacity-90 transition-all shadow-[0_0_16px_rgba(0,240,255,0.4)] flex items-center gap-1.5 active:scale-95"
            title="Trigger full-brain synaptic surge"
          >
            <Zap size={13} className="fill-black" />
            <span>SURGE SYNAPSES</span>
          </button>

          {/* Auto-Rotate Toggle */}
          <button
            onClick={() => setAutoRotate(!autoRotate)}
            className={`p-1.5 rounded-lg border text-xs transition-all ${
              autoRotate
                ? 'bg-cyber-surface border-neon-cyan/40 text-neon-cyan'
                : 'bg-cyber-surface/60 border-gray-700 text-gray-400'
            }`}
            title={autoRotate ? 'Pause Auto-Rotation' : 'Resume Auto-Rotation'}
          >
            {autoRotate ? <Pause size={14} /> : <Play size={14} />}
          </button>

          {/* Reset Camera Angle */}
          <button
            onClick={resetCamera}
            className="p-1.5 rounded-lg border border-gray-700 bg-cyber-surface/60 text-gray-400 hover:text-white hover:border-gray-500 transition-all"
            title="Reset 3D Perspective"
          >
            <RotateCcw size={14} />
          </button>

          {/* Sound Synthesizer Toggle */}
          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={`p-1.5 rounded-lg border text-xs transition-all ${
              soundEnabled
                ? 'bg-neon-magenta/20 border-neon-magenta text-neon-magenta shadow-[0_0_10px_rgba(255,0,229,0.3)]'
                : 'bg-cyber-surface/60 border-gray-700 text-gray-500'
            }`}
            title={soundEnabled ? 'Mute Neural Audio' : 'Enable Neural Audio Synthesizer'}
          >
            {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>

          {/* Speed Selector */}
          <select
            value={firingSpeed}
            onChange={(e) => setFiringSpeed(Number(e.target.value))}
            className="bg-cyber-surface border border-gray-700 rounded-lg px-2 py-1 text-xs text-gray-300 font-mono focus:border-neon-cyan focus:outline-none"
            title="Synaptic Firing Velocity"
          >
            <option value={0.6}>0.6x (Calm)</option>
            <option value={1.0}>1.0x (Normal)</option>
            <option value={1.8}>1.8x (Storm)</option>
          </select>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-lg border border-gray-700 bg-cyber-surface/60 text-gray-400 hover:text-white hover:border-gray-500 transition-all"
            title={isFullscreen ? 'Exit Fullscreen' : 'Expand Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Main 3D Canvas Area */}
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
          className="w-full h-[640px] block"
        />

        {/* Bottom Left Floating Telemetry HUD (Stark Tech Style) */}
        <div className="absolute bottom-4 left-4 p-3 rounded-xl bg-black/60 border border-white/10 backdrop-blur-md text-[11px] font-mono space-y-1 pointer-events-none">
          <div className="flex items-center gap-2 text-neon-cyan font-bold">
            <Activity size={12} className="animate-pulse" />
            <span>STARK NEURAL PROTOCOL // V4.8</span>
          </div>
          <div className="text-gray-400 flex items-center justify-between gap-4">
            <span>Synaptic Frequency:</span>
            <span className="text-white font-bold">{activeTelemetry.firingRate}</span>
          </div>
          <div className="text-gray-400 flex items-center justify-between gap-4">
            <span>Action Potential Pulses:</span>
            <span className="text-neon-green font-bold">{activeTelemetry.activePulses} active</span>
          </div>
          <div className="text-gray-400 flex items-center justify-between gap-4">
            <span>Neural Coherence:</span>
            <span className="text-neon-cyan font-bold">{activeTelemetry.coherence}</span>
          </div>
          <div className="text-gray-400 flex items-center justify-between gap-4">
            <span>Rendering Refresh:</span>
            <span className="text-gray-300">{activeTelemetry.fps} FPS (WebGL Canvas)</span>
          </div>
        </div>

        {/* Bottom Right Floating Instructions & Legend */}
        <div className="absolute bottom-4 right-4 hidden md:flex items-center gap-3 p-2.5 rounded-xl bg-black/60 border border-white/10 backdrop-blur-md text-[10px] font-mono text-gray-400 pointer-events-none">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-neon-cyan shadow-[0_0_8px_#00f0ff]" />
            <span className="text-gray-300 font-semibold">JARVIS (Cyan)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-orange-400 shadow-[0_0_8px_#ff9900]" />
            <span className="text-gray-300 font-semibold">ULTRON (Amber)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-neon-magenta shadow-[0_0_8px_#ff00e5]" />
            <span className="text-gray-300 font-semibold">Synaptic Bridge</span>
          </div>
          <span className="text-gray-500">| Drag to Rotate • Scroll to Zoom</span>
        </div>
      </div>
    </div>
  );
}
