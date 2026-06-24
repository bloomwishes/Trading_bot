/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'cyber-bg': '#0b0e14',
        'cyber-surface': '#141925',
        'cyber-card': '#161c2c',
        'cyber-border': '#232a3d',
        'neon-cyan': '#22d3ee',
        'neon-magenta': '#c084fc',
        'neon-green': '#34d399',
        'neon-yellow': '#fbbf24',
        'neon-red': '#fb7185',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        heading: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      transitionTimingFunction: {
        fluid: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      boxShadow: {
        'soft': '0 4px 24px -4px rgba(0,0,0,0.4)',
        'soft-lg': '0 12px 40px -8px rgba(0,0,0,0.5)',
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
