import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        command: {
          ink: "#14161a",
          panel: "#f4f7f8",
          line: "#ccd5d9",
          signal: "#0f766e",
          alert: "#b42318",
          amber: "#b7791f",
        },
      },
      boxShadow: {
        panel: "0 12px 28px rgba(20, 22, 26, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
