/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        obsidian: {
          DEFAULT: '#111110',
          50: '#2A2927',
          100: '#22211F',
          200: '#1A1918',
          900: '#111110',
          deep: '#0B0B0A',
        },
        graphite: {
          DEFAULT: '#242321',
          light: '#2E2D2A',
          card: '#191816',
          border: '#33312D',
          hover: '#383632',
        },
        gold: {
          DEFAULT: '#D6B779',
          light: '#E2CA97',
          dark: '#B89655',
          muted: '#8A7548',
          glow: 'rgba(214, 183, 121, 0.15)',
        },
        ivory: {
          DEFAULT: '#F5F0E7',
          soft: '#E8E1D3',
          muted: '#C4BCAB',
        },
        taupe: {
          DEFAULT: '#A49A89',
          light: '#BDB4A5',
          dark: '#6E6659',
        },
        verified: {
          DEFAULT: '#10B981',
          soft: 'rgba(16, 185, 129, 0.12)',
          border: 'rgba(16, 185, 129, 0.3)',
        },
        failure: {
          DEFAULT: '#EF4444',
          soft: 'rgba(239, 68, 68, 0.12)',
          border: 'rgba(239, 68, 68, 0.3)',
        }
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'gold-subtle': '0 0 20px -5px rgba(214, 183, 121, 0.18)',
        'gold-glow': '0 0 35px -5px rgba(214, 183, 121, 0.28)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
    },
  },
  plugins: [],
}
