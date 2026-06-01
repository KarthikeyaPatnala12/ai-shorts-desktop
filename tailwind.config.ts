import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#101316",
        panel: "#181e24",
        line: "#2c3742",
        mint: "#23c4b7"
      }
    }
  },
  plugins: []
};

export default config;
