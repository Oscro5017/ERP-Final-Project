/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        farm: {
          50: '#f3fbf3',
          100: '#e7f7e9',
          300: '#bfe4c3',
          600: '#2f7d4f',
          700: '#24643f',
          800: '#174b2f',
          900: '#103722',
        },
      },
      boxShadow: {
        soft: '0 10px 30px -12px rgba(15, 23, 42, 0.18)',
      },
    },
  },
  plugins: [],
};
