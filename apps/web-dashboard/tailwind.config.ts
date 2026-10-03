import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const hue = (name: string) => ({
  soft: token(`${name}-soft`),
  dot:  token(`${name}-dot`),
  ink:  token(`${name}-ink`),
});

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:            token("bg"),
        surface:       token("surface"),
        sunken:        token("sunken"),
        line:          token("line"),
        "line-strong": token("line-strong"),
        ink:           token("ink"),
        "ink-muted":   token("ink-muted"),
        "ink-faint":   token("ink-faint"),
        accent: {
          DEFAULT: token("accent"),
          hover:   token("accent-hover"),
          fg:      token("accent-fg"),
          soft:    token("accent-soft"),
        },
        sky:      hue("sky"),
        butter:   hue("butter"),
        lavender: hue("lavender"),
        sage:     hue("sage"),
        rose:     hue("rose"),
        peach:    hue("peach"),
        stone:    hue("stone"),
      },
      fontFamily: {
        sans:    ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-serif", "Georgia", "serif"],
        mono:    ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        soft:  "0 1px 2px rgb(var(--shadow) / 0.04), 0 1px 1px rgb(var(--shadow) / 0.03)",
        lift:  "0 12px 32px -8px rgb(var(--shadow) / 0.18), 0 2px 6px rgb(var(--shadow) / 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
