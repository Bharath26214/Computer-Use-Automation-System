/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        atlas: {
          navy: '#10263d',
          ink: '#1a3a57',
          teal: '#1f6f78',
          gold: '#c4a35a',
          sand: '#f4f1ea',
        },
      },
    },
  },
  plugins: [],
}
