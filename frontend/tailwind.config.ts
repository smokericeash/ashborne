import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#070607",
        obsidian: "#0b090b",
        panel: "#121012",
        elevated: "#1a1518",
        line: "#34262c",
        ashborne: {
          50: "#fff1f3",
          200: "#ffc2cc",
          300: "#ef6b85",
          400: "#d83a5f",
          500: "#b91c47",
          600: "#8f1838",
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(216,58,95,.12), 0 18px 64px rgba(0,0,0,.42)",
        signal: "0 0 22px rgba(216,58,95,.24)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)",
      },
      animation: {
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
        "slide-in": "slide-in .25s ease-out both",
      },
      keyframes: {
        "pulse-soft": {
          "0%,100%": { opacity: ".45" },
          "50%": { opacity: "1" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
