/**
 * Mirror of the Tailwind CDN `theme.extend` block in `core/templates/core/base.html`.
 * The live site uses the CDN config in the browser; this file exists for editors,
 * documentation, and a future PostCSS / CLI build if you add one.
 */
module.exports = {
  content: [
    "./core/templates/**/*.html",
    "./products/templates/**/*.html",
    "./core/static/**/*.js",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Playfair Display", "Georgia", "serif"],
      },
      colors: {
        background: "rgb(var(--color-bg-rgb) / <alpha-value>)",
        surface: "rgb(var(--color-surface-1-rgb) / <alpha-value>)",
        foreground: "rgb(var(--color-text-rgb) / <alpha-value>)",
        muted: "rgb(var(--color-text-muted-rgb) / <alpha-value>)",
        accent: "rgb(var(--color-accent-rgb) / <alpha-value>)",
        "accent-hover": "rgb(var(--color-accent-hover-rgb) / <alpha-value>)",
        danger: "rgb(var(--color-danger-rgb) / <alpha-value>)",
        "danger-soft": "rgb(var(--color-danger-soft-rgb) / <alpha-value>)",
        heading: "rgb(var(--color-heading-rgb) / <alpha-value>)",
        cream: "rgb(var(--color-cream-rgb) / <alpha-value>)",
        nav: "rgb(var(--color-nav-rgb) / <alpha-value>)",
        placeholder: "rgb(var(--color-placeholder-rgb) / <alpha-value>)",
        dim: "rgb(var(--color-dim-rgb) / <alpha-value>)",
        mist: "rgb(var(--color-mist-rgb) / <alpha-value>)",
        note: "rgb(var(--color-note-rgb) / <alpha-value>)",
        drift: "rgb(var(--color-drift-rgb) / <alpha-value>)",
        void: "rgb(var(--color-void-rgb) / <alpha-value>)",
        ink: "rgb(var(--color-ink-rgb) / <alpha-value>)",
        canvas: "rgb(var(--color-hover-rgb) / <alpha-value>)",
        elevated: "rgb(var(--color-elevated-rgb) / <alpha-value>)",
        track: "rgb(var(--color-track-rgb) / <alpha-value>)",
        mega: {
          paper: "rgb(var(--color-mega-paper-rgb) / <alpha-value>)",
          track: "rgb(var(--color-mega-track-rgb) / <alpha-value>)",
        },
        edge: "var(--color-border)",
        "edge-strong": "var(--color-border-strong)",
      },
    },
  },
  plugins: [],
};
