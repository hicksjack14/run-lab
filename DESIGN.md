---
name: Run Lab
description: Race-night telemetry for one runner's season. Warm charcoal, lime for pace, coral for heart rate.
colors:
  bg: "oklch(0.165 0.012 55)"
  raised: "oklch(0.205 0.014 55)"
  sunken: "oklch(0.135 0.012 55)"
  line: "oklch(0.3 0.014 55)"
  text: "oklch(0.94 0.01 80)"
  muted: "oklch(0.73 0.018 70)"
  faint: "oklch(0.58 0.016 65)"
  pace: "oklch(0.87 0.16 112)"
  heart-rate: "oklch(0.72 0.19 33)"
  good: "oklch(0.8 0.14 150)"
  improve: "oklch(0.82 0.15 78)"
  works: "oklch(0.8 0.11 205)"
  doesnt: "oklch(0.7 0.17 15)"
typography:
  body:
    fontFamily: "Familjen Grotesk, ui-sans-serif, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.5
  data:
    fontFamily: "DM Mono, ui-monospace, monospace"
  display:
    fontFamily: "Big Shoulders Display, sans-serif"
    fontWeight: 800
rounded:
  control: "8px"
  panel: "12px"
---

# Design System: Run Lab

## 1. Overview

**Creative North Star: "Race-Night Telemetry"**

Open after a run, at a laptop, in a dim room: precise, instrument-like, honest. Tools (Home, Runs, Planner) are calm and fast to read. Analytics is the one expressive page, with motion that shows change over time. It rejects generic SaaS analytics (rows of identical stat cards, default blue lines) and cutesy gamified fitness (badges, confetti).

**Key Characteristics:**
- Every number is monospaced; pace is lime, heart rate is coral, everywhere.
- A static topographic contour backdrop gives atmosphere without motion on tool pages.
- Motion only explains: playback, bars rising, dots flowing, rings filling. All of it degrades to a still picture under reduced motion.

## 2. Colors

A warm charcoal base with two data colors that never change meaning.

- **Pace Lime** (oklch(0.87 0.16 112)): pace lines, easy-pace text, the active nav marker.
- **Heart Coral** (oklch(0.72 0.19 33)): heart-rate lines and values.
- **Finding colors** (green good, amber improve, teal works, rose doesn't): only on findings and plan status.
- **Neutrals** are tinted toward the warm hue; never pure black or white.

**The Two-Colors Rule.** Lime always means pace and coral always means heart rate. Never reuse them decoratively.

## 3. Typography

Familjen Grotesk for text, DM Mono for all data and labels, Big Shoulders Display only on Analytics headlines and giant numerals.

- **Label:** DM Mono 0.7rem, uppercase, 0.08em tracking, faint.
- **Data:** DM Mono, tabular numerals, units in a smaller muted size.
- **Display (Analytics only):** 800 weight, uppercase, tight leading.

## 4. Elevation

Flat. Depth comes from tonal layers (sunken, bg, raised) and 1px lines, not shadows. The only shadow is the toast.

## 5. Components

- **Buttons:** 8px radius, 40px+ tall. Primary is off-white on charcoal; quiet is outlined.
- **Segmented controls:** one outlined group; the selected option inverts to off-white.
- **Panels:** 12px radius, 1px line border, never nested.
- **Findings:** a colored marker, headline, plain-language body, confidence bars and run count. Never a card grid.
- **Replay transport:** round play button, speed segments, large live readouts.

## 6. Do's and Don'ts

### Do:
- **Do** show sample size and confidence on every finding.
- **Do** keep tool pages still; put motion on Analytics only.
- **Do** keep every control 40px or taller with a visible focus ring.

### Don't:
- **Don't** build generic SaaS analytics: identical stat cards, default blue line charts.
- **Don't** add gamified fitness elements: badges, confetti, streak guilt.
- **Don't** use glowing neon, gradient text, or side-stripe borders.
- **Don't** use color alone to carry meaning; pair it with a label or position.
