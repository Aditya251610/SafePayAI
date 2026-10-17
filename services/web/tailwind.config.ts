import type { Config } from "tailwindcss";

// Colours are the Hard Cap tokens from styles/tokens.css. Every radius is
// zero; the only shadow is the hard slab.
const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    borderRadius: { none: "0", DEFAULT: "0" },
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        "panel-2": "var(--panel-2)",
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
        fg: "var(--fg)",
        mute: "var(--mute)",
        dim: "var(--dim)",
        seal: "var(--seal)",
        "seal-soft": "var(--seal-soft)",
        flare: "var(--flare)",
        "flare-soft": "var(--flare-soft)",
        ret: "var(--ret)",
        "ret-soft": "var(--ret-soft)",
        "on-seal": "var(--on-seal)",
        "on-ret": "var(--on-ret)",
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: { slab: "var(--slab)" },
      keyframes: {
        "agent-bar": {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(300%)" },
        },
      },
      maxWidth: { page: "1280px" },
    },
  },
  plugins: [],
};

export default config;
