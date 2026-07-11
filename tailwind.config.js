module.exports = {
  darkMode: "class",
  content: ["./app/templates/**/*.html", "./app/static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        agro: {
          50: "#f0fdf4",
          100: "#dcfce7",
          400: "#4ade80",
          500: "#22c55e",
          600: "#16a34a",
          700: "#15803d",
          800: "#166534",
          900: "#14532d",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
};
