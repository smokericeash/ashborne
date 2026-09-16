import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#05070b",
        obsidian: "#090d14",
        panel: "#0d131d",
        elevated: "#121b27",
        line: "#202c3a",
        kandor: {
          50: "#ecfffc",
          200: "#9df9ec",
          300: "#5de8d8",
          400: "#25cfbe",
          500: "#14ad9f",
          600: "#0c887f",
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(37,207,190,.15), 0 16px 60px rgba(0,0,0,.35)",
        signal: "0 0 22px rgba(37,207,190,.28)",
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
