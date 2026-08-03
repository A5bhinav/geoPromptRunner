import type { Config } from "tailwindcss";

const config: Config = {
  // No dark mode. Sable has no dark palette and the app has no toggle; a
  // half-invented one is how a sixth hue gets in.
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // The palette, by its real names. Semantic aliases below exist only so
        // the existing shadcn class names keep compiling during the migration —
        // new code should reach for navy/harbour/mist/paper directly.
        navy: "rgb(var(--navy-rgb) / <alpha-value>)",
        blue: "rgb(var(--blue-rgb) / <alpha-value>)",
        harbour: "rgb(var(--harbour-rgb) / <alpha-value>)",
        mist: "rgb(var(--mist-rgb) / <alpha-value>)",
        paper: "rgb(var(--paper-rgb) / <alpha-value>)",
        // Sky is NOT here. It exists only inside .on-navy — see tokens.css.

        border: "var(--rule)",
        input: "var(--rule)",
        ring: "rgb(var(--blue-rgb) / <alpha-value>)",
        background: "rgb(var(--paper-rgb) / <alpha-value>)",
        foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--navy-rgb) / <alpha-value>)",
          foreground: "rgb(var(--white-rgb) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--paper-rgb) / <alpha-value>)",
          foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "rgb(var(--paper-rgb) / <alpha-value>)",
          foreground: "rgb(var(--harbour-rgb) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--blue-rgb) / <alpha-value>)",
          foreground: "rgb(var(--white-rgb) / <alpha-value>)",
        },
        card: {
          DEFAULT: "rgb(var(--white-rgb) / <alpha-value>)",
          foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        },
        // `destructive`, `success` and `warning` are GONE. See the spec §6.
        // Leaving them aliased to navy would let `text-destructive` keep
        // compiling while silently doing nothing — the build error is the point.
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)", // 18
        lg: "var(--radius)", //              14
        md: "calc(var(--radius) - 2px)", //  12
        sm: "calc(var(--radius) - 4px)", //  10
      },
      fontFamily: {
        sans: ["var(--font-libre-franklin)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-cormorant)", "Georgia", "serif"],
      },
      // NO fontSize OVERRIDE. This is the obvious next move and it is a trap:
      // report-view.tsx uses text-sm / text-xs / text-base 37 times, so
      // redefining the scale would resize the CLIENT REPORT and repaginate the
      // PDF — a 17-page deliverable is not a place to discover a global type
      // change. The workshop scale is applied per-element in app code as
      // `text-[13px]` etc. Verbose on purpose: it cannot leak.
    },
  },
  plugins: [],
};

export default config;
