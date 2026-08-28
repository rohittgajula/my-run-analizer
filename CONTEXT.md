# my-run-analizer — living context

> **This file is Claude's responsibility to keep current.** It is the first thing a new
> session reads. If something here contradicts the code, the code wins and this file is
> stale — say so.

Last updated: **2026-08-28** · Status: **M3a + M3b complete. Race calendar and prediction resolve over real data. M3c (plan generator) next.**

---

## What this is

An AI running coach built around Garmin data. You give it **races with dates**; it builds
a training plan sized to the runway you actually have, adapts it every week from what you
really did, and predicts your finish as an honest range.

Repo: `github.com/rohittgajula/my-run-analizer` (name keeps the original spelling).
Local: `~/Desktop/MyRunAnalizer`. **Claude never commits and never pushes.** Git is
entirely Rohit's — staging, commit messages, history, remote. Claude edits files only.

Two rules shape everything:

> **Python calculates. The model interprets.**

> **"Distance" means distance *run*.** Not what the watch reported.

---

## The founding observation

A logged run reads **2.5 km**. Roughly **1.0 km of it was running**; the rest was walking.

Garmin's average pace over that is a blend of two different activities and describes
neither. Every metric built on it inherits the error, and a plan built on those metrics
prescribes for an athlete who does not exist.

So run/walk segmentation is not one calculator among many — it is the **first** thing,
and every downstream number takes segmented input. The metrics that matter are:

- `run_distance_m` / `walk_distance_m` / `run_fraction`
- `longest_continuous_run_m` and `_sec` ← **the single best progress signal for a beginner**
- `run_pace` measured over RUN blocks only
- `block_count`, mean block duration

For that run: 1.0 km run, 1.5 km walk, `run_fraction` 0.40, longest block 4:51.
Those are the numbers a coach needs. `2.5 km @ 8:27/km` is noise wearing a suit.

Segmentation keys on **cadence, not GPS speed** — a slow jog and a brisk walk overlap in
speed but not in cadence (≥140 spm ≈ running). Ported from `run-project`.

---

## Who is building what

| | |
|---|---|
| **Rohit** | Git — staging, commits, history, remote. Claude never runs git; it hands over a commit message. |
| **Claude** | Building, as of 2026-08-28: frontend *and* backend. |

**This changed at M1a.** The project was set up with Rohit writing all backend code so the
AI-integration layer would be learned by hand; he handed building over instead. M4–M6 —
the AI layer, and the stated reason the project exists — is the part worth checking before
Claude writes it.

The AI-integration layer is the thing worth learning by hand. Claude writes specs precise
enough to implement against — signatures, behaviour, test cases — and reviews what comes
back. Rohit types the backend.

**Exception, agreed at M0:** Garmin ingestion is *copied* from `run-project` rather than
retyped. Solved problem, no learning value left in it.

---

## Decided

| Question | Answer |
|---|---|
| Target race | **13 Dec 2026, 10K.** Reference data only — nothing structural may hardcode it. |
| Second race | **3 Jan 2027**, three weeks later. Multi-race is a requirement, not a later feature. |
| Gemini tier | **Paid from day one.** ~₹30–65/month — see [docs/COST.md](docs/COST.md). Free tier's data terms are not worth ₹40 on sleep, pain and mood logs. |
| Garmin auth | **Connect fresh** from this app's UI. No token sharing with `run-project`. |
| Pushing | **Rohit only.** Claude commits locally, never pushes. |
| Journal | **Mandatory after every run**, and an input to scheduling *and* prediction. |
| Hosting | **Public, with open registration.** Multi-tenancy stops being theoretical. Three consequences — unbounded AI cost, Garmin's per-IP rate limit, and holding other people's health data — are worked through in [docs/HOSTING.md](docs/HOSTING.md). |

---

## Three requirements that shape the architecture

### 1. Multiple races, not one date

Dec 13 and Jan 3 are **three weeks apart**, and this is the exact case `run-project` got
wrong: promoting a second race slid the whole ramp onto the new date and produced
**cutback, peak and taper with peak week landing eight days after a race.**

A **mode resolver runs before the plan generator** and answers, for any date, what that
date is *for*: `race` · `recovery` · `mini_taper` · `maintenance` · `build` · `off_season`.
Only `build` reads the week table. The others exist because the table has no row that is
right for those days.

One **A race** (`is_target`) anchors the ramp. Every B race is prescribed at its own
distance with its own short taper and recovery window, and **does not move the plan**.
Between two races closer than `MIN_BUILD_WEEKS`, the plan **holds at maintenance rather
than re-entering the ramp** — there is nothing to build in three weeks, and dropping
someone into `weeks_out=3` hands them a peak week on a recovering body.

The anchor falls back to the next race once the target passes. Without that, a passed
race leaves `weeks_out` clamped at 0 and prescribes **race week forever**.

### 2. Finish-time prediction, honestly

Wanted, and buildable — but the source plan's warning stands: no fabricated precision.
The output is a **range that visibly narrows as data accumulates**, which is both honest
and more motivating than a fake number.

Python computes the range. Gemini explains what it means and what would move it. Never
the reverse. Under 8 segmented runs across 3+ weeks it returns `insufficient_data` and
the UI shows no number at all. Full model: `docs/ROADMAP.md` § M3b.

### 3. The journal is a required input, not a nice-to-have

An activity is not complete until journalled, and **run analysis does not run without
one**. This is deliberate: the subjective read is the highest-value input in the system
and the only one Garmin cannot supply. RPE falling at constant pace is improving fitness
*before* pace moves.

Journal → LLM extraction → structured facts → **deterministic** readiness adjustment.
Say "tired" and next session eases. Say "pain" and progression stops. Those decisions are
Python, never the model — which is what keeps the "only ever easier" guarantee somewhere
a hallucination cannot reach. The failure mode of a bad extraction is a wrong *fact* the
athlete can see and correct, not a wrong prescription.

Escape hatch: "skip with reason" exists so a forgotten entry cannot deadlock the pipeline
forever. Skipped runs are analysed with an explicit `subjective_data: missing` flag.

---

## Prior art: `~/Desktop/run-project`

Working system for the same athlete (`github.com/rohittgajula/MarathonInsightPorject`).
Django 5 + DRF + Celery + Postgres + Redis + React/Vite. **Read its `CONTEXT.md` before
designing anything** — it records bugs already paid for.

### Lift near-verbatim

| File | Why |
|---|---|
| `apps/analysis/segmentation.py` | Run/walk split by cadence. **The most important file in either project.** |
| `apps/ingest/garmin.py` | Sync loop. Idempotent on Garmin activity id *and* file sha256. |
| `apps/ingest/garmin_connect.py` | Password→token exchange. Password never persisted or logged. |
| `apps/ingest/garmin_wellness.py` | Sleep / HRV / Body Battery / stress. |
| `apps/ingest/fit_parser.py` | `.fit` → per-second records. |
| `apps/ingest/weather.py` | Open-Meteo + Nominatim, no key needed. |

Take the *shape* of `plans/schedule.py` for the mode resolver, but rewrite it — its race
calendar logic is right and its 17-week anchoring is what this project removes.

### Hard-won facts that carry over

- Garmin has **no personal API**. This rides unofficial `garminconnect` on a saved OAuth
  token. Pin **0.3.10** everywhere — 0.2.x reads `oauth1_token.json`, 0.3.x writes a
  combined `garmin_tokens.json`, and mixing them fails confusingly.
- `garmin-mcp`'s CLI login sets `return_on_mfa=True`, short-circuiting the library's own
  `dump()` — it prints "Logged in" and **writes no token**. Confirm the token directory
  is non-empty after any login. `garmin_connect.py` leaves the flag at default for exactly
  this reason.
- Garmin's `*TimestampLocal` fields are epoch-ms **already shifted to local**. Applying a
  timezone on top double-counts.
- Garmin dates a night of sleep by the **morning it ends** — day D's sleep row is the sleep
  *before* D's session. Written notes are the opposite: they come from the evening before.
- Never `timezone.localdate()`. Django's `TIME_ZONE` is UTC and at 00:48 in Kolkata that
  is still yesterday. Go through the athlete's own local-today helper.
- **A log's date is not the day it was typed.** Ask which day's *session* an entry bears
  on, not which calendar day its words describe. "Last night I slept badly", written in
  the morning, is about *today's* session. Asked the other way the model answered
  "yesterday" — right about the words, wrong for the plan.
- **Never construct a `genai.Client()` inline.** As a single expression it can be GC'd
  mid-request; it closes its httpx pool on the way out and the call dies with "client has
  been closed". Cache clients in a module dict.
- A Gemini **rate limit is not a failure**. Give it its own status so the row is retried,
  not written off. Waiting the interval the error names does not reliably clear it.
- Readiness rules **only ever make a session easier**.
- Correlations were gated at 12 observations. Same discipline applies to prediction.

### Do not carry over

`run-project`'s plan engine anchors to one hardcoded 17-week table for one race. That
limitation is why this project exists.

---

## Stack (decided at M0)

**Backend** — Django 5 + DRF + Celery + Postgres + Redis, matching `run-project` so the
Garmin layer transplants cleanly and the framework is not the thing being learned.
Pydantic pulled in **specifically** for AI response validation.

**Frontend** — React 19 + TypeScript + Vite + TanStack Query + Recharts, **plus PWA**
(`vite-plugin-pwa`). Theme is pitch black with a **monochrome interface**; colour appears
only where it carries information. The tokens are in `src/styles.css` — `--ui` for
chrome, `--data` / `--ok` / `--bad` / `--warn` for meaning. Do not tint anything for
decoration; that rule is the whole design.

**AI** — Gemini primary, behind a provider-agnostic interface. Model IDs live in env
(`GEMINI_LITE_MODEL` / `GEMINI_FAST_MODEL` / `GEMINI_COACH_MODEL` / `GEMINI_DEEP_MODEL`),
never hardcoded. A second provider lands at M6 to prove the seam is real.

**Everything runs under `docker compose`** from day one.

### Installing to a phone

- **Android / Chrome** — valid manifest + service worker + HTTPS gets a native "Install
  app" prompt. Works as expected.
- **iOS** — installable **only from Safari's Share → Add to Home Screen**. iOS Chrome
  cannot install a PWA, and there is no Web Push until it is installed. The UI detects
  the browser and says the right thing rather than showing an Android prompt to an iPhone.

HTTPS required for both; localhost exempt in development.

---

## Repo layout (target)

```
my-run-analizer/
├── backend/
│   ├── config/            settings, celery, urls
│   ├── apps/
│   │   ├── athletes/      Athlete — tenancy root, bands, training_days, timezone
│   │   ├── ingest/        Garmin sync, .fit parsing, wellness, weather   [copied]
│   │   ├── activities/    Activity, per-second records, blocks, metrics
│   │   ├── analysis/      pure calculators + segmentation — NO Django imports
│   │   ├── planning/      race calendar, mode resolver, generator, prediction
│   │   ├── coaching/      the AI layer — client, prompts, schemas, validators
│   │   └── journal/       mandatory post-run entry, extraction, readiness
│   ├── requirements.txt
│   └── manage.py
├── frontend/              React + TS + Vite + PWA          [Claude writes]
├── docs/
│   ├── ROADMAP.md         the build plan and its milestones
│   ├── COST.md            token volumes and the monthly bill
│   └── source-plan-gemini.md
├── docker-compose.yml
├── .env.example
└── CONTEXT.md             ← you are here
```

`analysis/` and `planning/` staying free of Django imports is not stylistic. It is what
lets segmentation, metrics, the calendar and the generator be tested without a database,
which is where most of the tests live.

---

## Running it

```bash
cd ~/Desktop/MyRunAnalizer && docker compose up -d
```

Frontend http://localhost:5173 · API http://localhost:8000/api/health/ · admin `/admin`.
Tests: `docker compose exec backend python -m pytest tests/ -q`.

**Python dependencies live in the image.** After editing `requirements.txt`:
`docker compose build backend && docker compose up -d --force-recreate backend worker beat`.
A plain `up -d` does not pick them up and the failure looks like a `ModuleNotFoundError`
in code you just verified.

`.env` is gitignored and already copied from `.env.example`. **Add `GEMINI_API_KEY` and
the four model IDs there** — nothing reads a model name from code.

## Current state

**M0–M2, M3a, M3b done.** Accounts, Garmin ingestion, the metrics engine, the race
calendar and finish prediction all work against real data. **109 tests pass.**

Races stored: **Bajaj Pune 10K, 13 Dec 2026 (target)** and **January 10K, 3 Jan 2027**.
Today resolves to `build`, 15 weeks out — a STANDARD runway for a 10K.

The Dec/Jan calendar resolves correctly, which was the whole point of M3a:
`build` → race → 7 days `recovery` → `maintenance` (1.9 weeks to the next race, under
`MIN_BUILD_WEEKS`, so it holds rather than rebuilding) → 3 days `mini_taper` → race →
`recovery`. No build day falls inside a recovery window, and no peak week lands after
a race — both are property-tested over the full range.

**Prediction currently returns INSUFFICIENT_DATA**, and that is the system working:
7 segmented runs over 2.1 weeks against a gate of 8 over 3. One more run and about a
week of history opens it.

**18 real activities imported**, back to 2 July: 8 runs, 5 walks, 4 strength sessions,
1 ride. 12 segmented; the strength and cycling sessions are refused rather than
mis-segmented.

### What segmentation found

The 17 Aug session, which started this project:

| | |
|---|---|
| Garmin says | 2651 m @ **10:29/km**, avg cadence 116 |
| Actually | **976 m run** in 5 blocks, 1522 m walked (37%), 120 s stopped |
| Real running pace | **8:27/km** (walking 11:21/km, blended 9:43/km) |
| Longest unbroken block | 4:51 |

Garmin's 10:29/km is two minutes per km slower than his actual running pace, because it
averages running, walking and standing still. Avg cadence 116 is below the 140 running
threshold for the same reason.

**The clearest finding in the data is a deliberate trade.** From 18 Aug the athlete
slowed from ~8:20/km to ~10:20/km, and the longest continuous block went 4:48 → 10:12 →
13:54. Running easier let him run roughly three times longer. That is textbook-correct
beginner behaviour and the single best thing in the history.

It also broke the first version of the predictor: a trend fit on pace read the
slowdown as decline and projected him slower still, compounding into a **four-hour
10K** — slower than walking it. Pace is now *estimated* from the recent median rather
than extrapolated, and two bounds are enforced: a finish can never be slower than
walking the distance, nor faster than the best pace ever run. Both are tested.

21 Aug breaks the pattern — 6 blocks, longest 3:00, but 1327 m of running — which reads
as an interval session rather than a regression.

### Deviations from `run-project` worth knowing### Deviations from `run-project` worth knowing

- **The FIT parser produces its own `ParsedRecord`** rather than importing
  `analysis.segmentation.Sample` and smuggling extra fields through `__dict__`. The
  parser now imports nothing from the app: it produces data, segmentation consumes it.
- **`segmentation_version` (int) rather than `metrics_current` (bool)** — a flag says a
  row is stale but never how stale. An integer makes "everything before v4" a query and
  tells you which algorithm produced any given number.
- **`available_days` holds availability only**, not day types. The generator owns what
  each day is for.
- **Segmentation refuses rather than guesses.** `check_segmentable` rejects non-foot
  sports and activities below 70% cadence coverage. `run-project` would classify a
  whole cycling session as "stop" and report it as a real measurement.
- **Speed integration uses real time deltas**, not an assumed 1 Hz. Garmin drops to
  smart recording on long activities, where assuming one sample per second understates
  distance.

### Bugs caught during M1a/M1b, each of which would have cost an afternoon

- **`ingest_fit` marked failures inside its own `@transaction.atomic`**, so
  `status=FAILED` and the error text were rolled back with everything else. A bad file
  would sit at PENDING forever, retried, with nothing anywhere saying why. Failure
  marking now lives outside the transaction; the writes stay inside it.
- **Worker and beat ran a stale image.** Compose builds a *separate* image per service
  from the same context unless `image:` is set, so `docker compose build backend` left
  the other two behind and they died with `ModuleNotFoundError` for a package the
  backend visibly had. All three now share one image.
- **Registration silently skipped onboarding.** Adopting the session re-rendered the
  route guards, and the guard's redirect to `/` beat `navigate('/onboarding')` every
  time. Fixed with an explicit `onboarding_complete` flag — the router reads data, it
  does not race a redirect.
- **`npm run build` failed on TS narrowing** in a hoisted `async function` capturing a
  nullable state value. Arrow consts are created after the guard, so narrowing holds.
- **The day picker wrapped**, stretching Sunday to full width. Grid, not `flex-wrap`.

### Four things fixed during M1a, each of which would have cost an afternoon

- **Worker and beat ran a stale image.** Compose builds a *separate* image per service
  from the same context unless `image:` is set, so `docker compose build backend` left
  the other two behind and they died with `ModuleNotFoundError` for a package the
  backend visibly had. All three now share one image.
- **Registration silently skipped onboarding.** Adopting the session re-rendered the
  route guards, and the guard's redirect to `/` beat `navigate('/onboarding')` every
  time. Fixed with an explicit `onboarding_complete` flag — the router reads data, it
  does not race a redirect.
- **`npm run build` failed on TS narrowing** in a hoisted `async function` that captured
  a nullable state value. Arrow consts are created after the guard, so narrowing holds.
- **The day picker wrapped**, stretching Sunday to full width in a narrow card. Grid with
  seven equal columns, not `flex-wrap`.

### Open

- **`DJANGO_SECRET_KEY` signs the JWTs**, and the dev default is 26 chars — under the
  32-byte minimum for HMAC-SHA256. Fine locally, **forgeable tokens on a public host**.
  Generate one before hosting: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
- **Service-worker registration is still unverified.** This browser blocks it by policy.
  Artifacts are correct; confirm the real install on a phone over HTTPS.
- Timezone arrives from browsers as `Asia/Calcutta` (a valid legacy alias for
  `Asia/Kolkata`). Works correctly; only looks odd.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-08-19 | Django over FastAPI | Garmin layer transplants unchanged; free admin for inspecting AI rows; framework is not the learning target. |
| 2026-08-19 | Copy Garmin ingestion | Solved problem. Effort goes to metrics, planning and the AI layer. |
| 2026-08-19 | Races are input; multiple races supported | Dec 13 + Jan 3 is the case a single-date plan gets actively wrong. |
| 2026-08-19 | PWA, not native | One codebase; installs on Android from Chrome, iOS from Safari. |
| 2026-08-19 | Segmentation is the foundation, not a metric | The 2.5 km / 1.0 km gap makes every unsegmented number wrong. |
| 2026-08-19 | Prediction ships as a gated range | Wanted and useful; a point estimate off 6 runs would be fiction. |
| 2026-08-19 | Journal mandatory, gates run analysis | Highest-value input, and the only one Garmin cannot supply. |
| 2026-08-19 | Public registration | Being hosted for others, not just Rohit. Adds throttling at M1a, a per-user AI budget at M5, and a hardening pass before launch. |
| 2026-08-28 | Claude builds, Rohit owns git | Reverses the original split. M4–M6 still worth a conversation before Claude writes it. |
| 2026-08-28 | `onboarding_complete` as a real field | The router must read a flag, not race a redirect. |
| 2026-08-19 | JWT, split storage | Access token in JS memory (15 min), refresh token in an httpOnly cookie with rotation + blacklist. `localStorage` was rejected: XSS can read it, and a JWT there cannot be revoked on logout. |
| 2026-08-19 | Paid Gemini from day one | ₹30–65/month. Free tier trains on health logs; not a trade worth ₹40. |
| 2026-08-19 | Claude never touches git | Rohit owns staging, commits, history and the remote. |
| 2026-08-19 | M0 scaffolds the shell only | No apps, no routing beyond one health URL. Pre-creating apps would be Claude writing the backend by the back door. |
| 2026-08-19 | Frontend deps resolved by npm, not pinned by guess | React 19, TS 7, Vite 6, vite-plugin-pwa 1.3 — real current versions in `package-lock.json`. |
| 2026-08-28 | Monochrome UI, colour only for meaning | `#000` base, greyscale chrome (`--ui #ededf2`), and saturation reserved for information: `--data` cyan for measured values, `--ok` / `--bad` / `--warn` for state. The earlier electric-green accent was effectively Runna's palette. This version is the app's own premise made visual — when a pain flag turns something red it lands, because nothing else competes for attention. |
| 2026-08-28 | Icon generator lives in the repo | `frontend/scripts/make-icons.py`, pure zlib + struct, no image library. Icons are reproducible rather than one-off binaries. |
