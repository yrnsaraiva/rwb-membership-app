/** @type {import('tailwindcss').Config} */
// As cores apontam para variáveis CSS (static/css/components.css), que mudam com o tema claro/escuro.
const themeColors = {
  bg: "var(--bg)",
  surface: "var(--surface)",
  surface2: "var(--surface-2)",
  line: "var(--line)",
  fg: "var(--fg)",
  soft: "var(--soft)",
  muted: "var(--muted)",
  accent: "var(--accent)",
  danger: "var(--danger)",
  brand: "var(--brand)",
  "brand-dark": "var(--brand-dark)",
  "brand-ink": "var(--brand-ink)",
};

module.exports = {
  content: ["./templates/**/*.{html,svg,js}", "./apps/**/*.py", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: themeColors,
      fontFamily: {
        display: ["Oswald", "Arial Narrow", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
module.exports.themeColors = themeColors;
