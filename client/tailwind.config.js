/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        coffee: {
          50: "#f7f4f0",
          100: "#efe5d8",
          200: "#e3cfba",
          300: "#d3b38f",
          400: "#c59a6f",
          500: "#a67c52",
          600: "#8a633f",
          700: "#6d4b33",
          800: "#583b2d",
          900: "#4a3228",
        },
        gold: "#c9a86a",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        display: ["Poppins", "Inter", "ui-sans-serif"],
      },
    },
  },
  plugins: [],
}
