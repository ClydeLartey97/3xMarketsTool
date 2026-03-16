import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#08111a",
        slate: "#0f1d2b",
        mist: "#dce7f2",
        signal: "#f97316",
        positive: "#0f9f7c",
        caution: "#d97706",
        danger: "#d14343",
      },
      boxShadow: {
        panel: "0 18px 45px rgba(7, 17, 27, 0.12)",
      },
      fontFamily: {
        sans: ["Avenir Next", "Segoe UI", "Helvetica Neue", "sans-serif"],
        display: ["Iowan Old Style", "Palatino", "Book Antiqua", "serif"],
      },
    },
  },
  plugins: [],
};

export default config;
