# my-run-analizer

An AI running coach built on Garmin data. Pick a **race date and a distance**; the system
builds a training plan sized to the runway you actually have, then adapts it each week
from what you really did.

One rule shapes the architecture:

> **Python calculates. The model interprets.**

Paces, drift, volume, phase boundaries and every safety gate are deterministic Python.
The LLM reads those numbers and says what they mean and what to do next. It never does
arithmetic and never has the last word on a plan.

## Documents

- **[CONTEXT.md](CONTEXT.md)** — current state, decisions, and the traps already paid for
  in the previous project. Read this first.
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — the build plan, milestone by milestone.
- **[docs/source-plan-gemini.md](docs/source-plan-gemini.md)** — the original 17-week
  design this generalises.

## Status

M0 — scaffolding. No application code yet.
