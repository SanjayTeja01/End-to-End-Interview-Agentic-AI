import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: { 50: "#f3f0ff", 100: "#e4dcff", 500: "#9b85ff", 600: "#7c5cff", 700: "#5b3fd6" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
