/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'cyber-bg': '#0a0a0f',
        'cyber-surface': '#1a1a2e',
        'cyber-card': '#16213e',
        'neon-cyan': '#00f0ff',
        'neon-magenta': '#ff00e5',
        'neon-green': '#00ff88',
        'neon-yellow': '#ffd600',
        'neon-red': '#ff3366',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        heading: ['Rajdhani', 'Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'slide-in': 'slide-in 0.3s ease-out forwards',
        'fade-in': 'fade-in 0.4s ease-out forwards',
        'shimmer': 'shimmer 2s linear infinite',
        'pulse-dot': 'pulse-dot 1.5s ease-in-out infinite',
        'glow-border': 'glow-border 3s ease-in-out infinite',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 5px rgba(0, 240, 255, 0.2)' },
          '50%': { boxShadow: '0 0 25px rgba(0, 240, 255, 0.5)' },
        },
        'slide-in': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.5', transform: 'scale(1.5)' },
        },
        'glow-border': {
          '0%, 100%': { borderColor: 'rgba(0, 240, 255, 0.2)' },
          '50%': { borderColor: 'rgba(0, 240, 255, 0.6)' },
        },
      },
      backgroundImage: {
        'cyber-gradient': 'linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #16213e 100%)',
        'neon-gradient': 'linear-gradient(90deg, #00f0ff, #ff00e5)',
        'green-gradient': 'linear-gradient(90deg, #00ff88, #00f0ff)',
      },
    },
  },
  plugins: [],
};
