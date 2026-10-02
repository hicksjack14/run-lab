# Product

## Register

product

## Users

One person: Jack, a college student who started running in spring 2026 and now trains toward race goals (5K to marathon). He opens Run Lab at his laptop in the evening after a run, or on a rest day while planning the week. He already logs everything in Strava and a Garmin watch; he wants his own sharper view of it, tied to the music he runs to. He is a beginner at coding but comfortable reading numbers and charts.

## Product Purpose

A personal, local-first running lab. It pulls every run from Strava, shows the exact stats and a live map replay of each one, works out his easy and hard paces and heart-rate zones from his own data, plans training toward a goal race (exportable to Google Calendar), and lines up the songs he listened to with his pace and heart rate. An Analytics page turns the whole season into honest, plain-language findings: what he does well, what to fix, what works for him and what does not. Success is that after every run he learns something specific about himself, and that every planned workout has a clear pace and purpose.

The primary surface is a tool (home, runs, planner). Analytics is the one expressive showpiece.

## Brand Personality

Race-night telemetry: precise, instrument-like, measured. Direct like a coach who knows your numbers. Three words: precise, honest, kinetic.

References: Strava (activity-first structure, athletic tone) and Spotify Wrapped (big animated story moments, used on the Analytics page only).

## Anti-references

- Generic SaaS analytics: rows of identical stat cards and default blue line charts.
- Cutesy gamified fitness: badges, confetti, mascots, streak guilt.
- Neon-on-black dashboard clichés and decorative glassmorphism.

## Design Principles

1. **Every number traces to a run.** Any stat or finding can be clicked back to the runs and samples behind it.
2. **Say it straight.** Findings are written like a coach talking, with the sample size and confidence stated. Never oversell a pattern from a few runs.
3. **Motion explains or it doesn't ship.** Animation shows change over time, progress, or relationships. No decorative loops on tool pages.
4. **Calm tools, one showpiece.** Home, Runs, and Planner are fast and quiet; Analytics earns its drama.
5. **Local and private.** GPS, heart rate, and listening history never leave his machine; design never implies sharing.

## Accessibility & Inclusion

WCAG AA contrast. `prefers-reduced-motion` is respected everywhere (animated pages degrade to a static, still-informative view). Color is never the only carrier of meaning: pace and heart rate are also distinguished by labels, position, and line style. Keyboard operable (replay, scrubbing, plan editing).
