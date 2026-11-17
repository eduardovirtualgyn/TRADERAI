/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: "#080B10",
          800: "#0F141C",
          700: "#17202E",
          600: "#222E42",
          500: "#32435F",
        },
        even: {
          DEFAULT: "#00E5FF",
          glow: "rgba(0, 229, 255, 0.25)",
        },
        odd: {
          DEFAULT: "#FF7700",
          glow: "rgba(255, 119, 0, 0.25)",
        },
        accent: {
          green: "#10B981",
          red: "#EF4444",
          amber: "#F59E0B",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
