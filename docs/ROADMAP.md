# Build plan

Milestones. Each names the files Rohit writes, the signatures to write them against, and
a **done test** — a thing that either passes or doesn't. No milestone is finished on the
strength of "it looks right".

Claude writes the frontend and the specs. Rohit writes the backend.

Ordering principle: the AI integration is not glue bolted on at the end. It is three
milestones (M4–M6), built in layers, because that is the thing being learned. Everything
before it exists to give those layers something honest to talk about.

---

## M0 — Scaffold · *shared*

`docker compose up -d` brings up backend, worker, beat, db, redis, frontend.
`GET /api/health/` returns `{"status": "ok", "db": true, "redis": true}` — it actually
touches both rather than returning a constant.

**Rohit:** Django project, `config/settings.py`, `config/celery.py`, the health view.
**Claude:** `docker-compose.yml`, both Dockerfiles, `.env.example`, the Vite scaffold.

Two things `run-project` got wrong that are cheap now and expensive later:

- Set `STATIC_ROOT` immediately. Without it the admin loses its CSS the moment `DEBUG=0`,
  and you find out during a deploy.
- Dockerfiles run `gunicorn`, not `runserver`, with a dev override in compose.

Python dependencies live in the image. After touching `requirements.txt`:
`docker compose build backend && docker compose up -d --force-recreate backend worker beat`.
A plain `up -d` does not pick them up and the failure looks like a `ModuleNotFoundError`
in code you just verified.

**Done:** health endpoint green, `pytest` runs, frontend serves.

---

## M1 — Data model + Garmin transplant

### Models

Follow the source plan's §6 tables with these deviations:

- **`TrainingGoal.weeks` is derived, never stored** — it is `race_date - plan_start`.
- **`Race` is a table, not a field.** `is_target` marks the A race. Multiple races are a
  day-one requirement, not a later feature.
- **`TrainingWeek` gets `generation` and `is_projection`.** The plan is regenerated weekly
  from real data. Week 9 as forecast in week 1 and week 9 as prescribed in week 8 are
  different rows, and diffing them is one of the more interesting things this can show.
- **`Workout.phase` and `plan_week` are nullable.** A recovery day after a B race is not
  "week 15 of 20". Printing a week number over one is the plan claiming a position it has
  left.
- **`Activity.journalled` (bool) + `journal_skipped_reason`.** M7 gates analysis on this.
- **`AIAnalysis` carries `prompt_version`, `model`, `input_hash`.** Non-negotiable —
  without them you cannot tell a model change from a prompt change from a data change.

Apps: `athletes`, `ingest`, `activities`, `analysis`, `planning`, `coaching`, `journal`.
`Athlete` is the tenancy root from day one with a scoped-queryset mixin every view uses.
Retrofitting multi-tenancy is a bad week.

### Garmin — copy

From `~/Desktop/run-project/backend/apps/ingest/`: `garmin.py`, `garmin_connect.py`,
`garmin_wellness.py`, `fit_parser.py`, `weather.py`. Pin `garminconnect==0.3.10`.

Connect fresh from the UI — no token sharing with `run-project`. Read the files as you
paste; the comments record real failures. Then re-read the Garmin section of `CONTEXT.md`
— the timezone and sleep-dating traps are both silent.

**Done:** sync imports real activities, is safe to re-run (second run reports all-skipped),
stores raw `.fit` bytes permanently so a better parser can be re-run over history.

---

## M2 — Segmentation and metrics · *pure Python*

`apps/analysis/` — **no Django imports anywhere in this package.**

### Segmentation comes first, and everything else consumes it

A logged run reads 2.5 km; 1.0 km of it was running. Garmin's average pace over that
blend describes neither activity. Port `segmentation.py` from `run-project` **before**
writing any other calculator, because every other calculator takes its output.

```python
ALGORITHM_VERSION = 3
def segment(records: list[Record]) -> list[Block]   # RUN | WALK | STOP
    # Keys on CADENCE, not GPS speed. A slow jog and a brisk walk overlap in
    # speed but not cadence (>=140 spm ~ running).
```

Then the metrics that actually describe a beginner:

```python
# analysis/running_truth.py — the numbers this project exists to produce
def run_distance_m(blocks) -> float
def walk_distance_m(blocks) -> float
def run_fraction(blocks) -> float                  # 0.40 for the founding example
def longest_continuous_run(blocks) -> tuple[float, float]   # (metres, seconds)
def run_pace_sec_per_km(blocks) -> float | None    # RUN blocks ONLY
def block_count(blocks) -> int
```

`longest_continuous_run` is **the single best progress signal for a beginner** — more
informative than distance, pace or heart rate, and it is what the prediction model in M3b
is built on. 4:51 today; the question the whole system answers is what it will be in
December.

### The rest

```python
# analysis/pace.py
def splits_from_records(records, every_m=1000) -> list[Split]
def pace_variability(splits) -> float              # coefficient of variation, %
def half_split(splits) -> tuple[float, float]
def is_negative_split(splits) -> bool

# analysis/heart_rate.py
def hr_drift_percent(records) -> float | None
    # (2nd-half mean HR - 1st-half mean HR) / 1st-half mean HR * 100
    # None when HR covers under 80% of moving time. Returning 0.0 for missing
    # data is a lie the whole stack then repeats.
def hr_recovery_60s(records, block_end_idx) -> int | None
    # Measured FROM PEAK, not the block boundary. Cardiac lag keeps HR climbing
    # 15-25s after stopping; measuring from the boundary understates recovery on
    # exactly the athletes who need it measured.

# analysis/cadence.py
def cadence_variability(records) -> float
def cadence_by_split(splits) -> list[float]
    # No universal 180spm target. Report the trend; let the model read context.

# analysis/load.py
LOAD_FORMULA_VERSION = "v1"
def session_load(duration_min, effort_factor) -> float
def rolling_load(sessions, days) -> float
    # Call it "Custom Training Load" in every UI string. It is not Garmin's.
```

Two rules that will save you:

- **`None` means unknown. `0` means measured zero.** Conflating them produces a system
  confidently reporting trends in data it does not have.
- **Version the algorithms.** Bump on any behavioural change, then re-derive across
  history. Without this a metric silently means two different things in your own database.

**Done:** ~40 unit tests on hand-built fixtures — empty, single-sample, no-HR, mid-run
pause, and **the founding case**: a 2.5 km activity that is five run blocks totalling
1.0 km must report `run_distance_m ≈ 1000`, `run_fraction ≈ 0.40`, `longest ≈ 4:51`.
No database.

---

## M3a — Race calendar and mode resolver · *pure Python*

**Build this before the generator.** Given a set of races and a date, what is that date
*for*?

Dec 13 and Jan 3 are **three weeks apart**, and this is precisely where `run-project`
failed: promoting a second race slid the whole ramp and produced cutback, peak and taper
with **peak week landing eight days after a race**.

```python
Mode = Literal["race", "recovery", "mini_taper", "maintenance", "build", "off_season"]

def resolve_mode(day: date, races: list[Race], config: PlanConfig) -> ModeResult
```

Rules:

- **One A race** (`is_target`) anchors the ramp. Only `build` reads the week table.
- **B races** get their own distance, their own short taper (days, not weeks) and their
  own recovery window. They **do not move the ramp**.
- **Recovery** ≈ one day per mile, rounded **up**. 6.2 rounds down to a window that hands
  straight over to a long run with no easing step.
- **Between races closer than `MIN_BUILD_WEEKS`** (~4): hold at **maintenance**. There is
  nothing to build in three weeks, and dropping someone into `weeks_out=3` gives them a
  peak week on a recovering body.
- **The anchor falls back to the next race once the target passes.** Without this a passed
  race leaves `weeks_out` clamped at 0 and prescribes race week forever.

**Done — the Dec 13 + Jan 3 case, explicitly:**

| Dates | Expected |
|---|---|
| → Dec 12 | `build`, counting down to Dec 13 |
| Dec 13 | `race` |
| Dec 14–20 | `recovery` (10K ≈ 6.2 mi → 7 days) |
| Dec 21–30 | `maintenance` — **not** a rebuild, the gap is under `MIN_BUILD_WEEKS` |
| Dec 31 – Jan 2 | `mini_taper` |
| Jan 3 | `race` |
| Jan 4+ | `recovery`, then `off_season` with no further race |

Plus: no race at all → `off_season` throughout. Races on the same day → rejected at the
boundary. **No `build` day may fall inside any recovery window** — property-test it.

---

## M3b — Finish-time prediction · *pure Python*

The source plan pushed this to "later" and warned against fake precision. Both concerns
are met by predicting a **range that narrows as data accumulates** rather than a number.

### Inputs — all from M2, all segmentation-derived

Trends over the last 6–8 weeks of `longest_continuous_run_sec`, `run_fraction`,
`run_pace` at comparable HR, and RPE at comparable pace (from the journal — RPE falling
at constant pace is improving fitness *before* pace moves).

### Model

```python
def predict_finish(race: Race, history: list[RunSummary], config) -> Prediction
```

1. **Project continuous capacity to race date.** Damped linear fit on
   `longest_continuous_run_sec` — beginners improve fast then plateau, and an undamped
   line extrapolates a first-timer to a marathon.
2. **Project run pace** at controlled effort.
3. **Branch:**
   - Projected capacity ≥ race distance × 1.1 → **continuous**. Riegel
     (`T2 = T1 × (D2/D1)^k`) from the best recent sustained effort, with `k ≈ 1.10–1.15`
     rather than the classic 1.06 — Riegel is fitted on trained runners and flatters
     beginners over longer distances.
   - Otherwise → **run/walk**:
     `time ≈ distance × [f × run_pace_adj + (1 − f) × walk_pace]`
     where `f` is projected run fraction at race distance and `run_pace_adj` carries a
     fade factor for distance beyond the demonstrated longest.

### Output

```python
{
  "mode": "RUN_WALK",
  "likely_finish_sec": 4680,
  "range_sec": [4320, 5220],
  "confidence": "LOW",
  "observations": 6,
  "basis": "6 segmented runs over 3 weeks; longest continuous block 4:51",
  "what_would_change_it": [
    "longest continuous block reaching 15 minutes",
    "run_fraction above 0.7 on a 5 km session"
  ]
}
```

**The gate is the whole design.** Under 8 segmented runs spanning 3+ weeks → return
`insufficient_data` and the UI shows **no number at all**. `run-project` gated
correlations at 12 observations for the same reason.

Python produces the range. Gemini explains what it means and what would move it. Never
the reverse — a model asked to predict a finish time will produce a confident number from
nothing.

**Done:**

| Case | Expected |
|---|---|
| 6 runs | `insufficient_data`. No number rendered. |
| 20 runs, flat trend | Range brackets current ability; `confidence: LOW/MODERATE`. |
| 20 runs, improving | Range shifts faster; upper bound tightens. |
| Capacity ≥ distance | Switches to `CONTINUOUS`, Riegel path. |
| Any input | `range_sec[0] < likely < range_sec[1]`, all positive. Property-test. |
| Any input | More observations never *widens* the range. Property-test. |

---

## M3c — Plan generator · *pure Python*

Runs **only** for dates `M3a` resolved to `build`. Everything else is prescribed by mode.

### Step 1 — runway

```python
weeks_available = full_weeks_between(plan_start, target_race.date)
```

### Step 2 — classify

```python
MIN_SAFE_WEEKS  = {"5K": 6,  "10K": 8,  "HM": 12, "M": 16}
IDEAL_MAX_WEEKS = {"5K": 12, "10K": 18, "HM": 22, "M": 24}
```

- `< MIN_SAFE` → **SHORT.** Build what fits. **Do not compensate by ramping faster than
  the safety cap** — that is the exact trade that injures people, and the one an eager
  system makes by default. Set `runway_warning`; the UI says plainly that the goal is
  finishing, probably run/walk.
- `MIN_SAFE … IDEAL_MAX` → **STANDARD.**
- `> IDEAL_MAX` → **EXTENDED.** Prepend a `BASE` block of `weeks − IDEAL_MAX` at
  maintenance, then STANDARD over the tail. Do not stretch an 18-week ramp across 40; you
  get a plan too slow to adapt to that peaks nowhere.

### Step 3 — allocate phases across `N` weeks

```python
race       = 1
taper      = 1 if distance <= 10K else 2 if distance <= HM else 3
peak       = max(1, round(0.12 * N))
specific   = max(2, round(0.28 * N))
aerobic    = max(2, round(0.26 * N))
foundation = N - (race + taper + peak + specific + aerobic)
```

If `foundation < 2`, shave one week at a time from the largest discretionary block —
`specific`, then `aerobic`, then `peak`. Deterministic, therefore testable, which is the
whole point of doing it here rather than asking a model.

### Step 4 — volume ramp

- `start_volume_km` — **derived from actual last-4-weeks Garmin data**, not a
  questionnaire. People misreport this, always upward.
- **Progress `run_distance`, not total distance.** Ramping total volume when 60% is
  walking prescribes a load the athlete is not actually carrying.
- Cap week-on-week increase at `MAX_WEEKLY_INCREASE_PCT` (default 10).
- Cutback every 3rd–4th week at ×0.7. Non-negotiable; adaptation happens there.
- Taper 60% then 40% of peak. Race week 30% plus the race.

### Step 5 — lay sessions across `athlete.training_days`

Real available days, not an idealised Mon/Wed/Fri. Hard sessions never on consecutive
days. Long run on the day they said they have time.

```python
# planning/generator.py — pure, no Django
def generate_plan(races, plan_start, baseline, config) -> Plan
```

**Done:**

| Case | Expected |
|---|---|
| 17 weeks, 10K | Roughly matches the source plan's table. Sanity anchor. |
| 5 weeks, 10K | `SHORT`. No week exceeds the cap. Warning set. |
| 40 weeks, 10K | `EXTENDED`. Base block, then a normal-shaped ramp. |
| 8 weeks, marathon | `SHORT`, strongest warning. Still returns a plan. |
| Race tomorrow | Race week only. No crash, no negative weeks. |
| Race in the past | Rejected at the boundary with a clear error. |
| Dec 13 + Jan 3 | Ramp targets Dec 13 only. Jan 3 gets taper + recovery, moves nothing. |
| Any runway | Phase weeks sum exactly to `weeks_available`. **Property-test.** |
| Any runway | No two hard sessions on consecutive days. **Property-test.** |

The property tests matter most. They are invariants, and a few hundred random
(date, distance, race-set) tuples find the off-by-one that a handful of examples will not.

---

## M4 — AI layer I: getting a structured answer out of a model

**The milestone to slow down on.** Do not skip to the SDK because it is right there — the
point of step 1 is that when the SDK misbehaves at M6 you will know what it was supposed
to be doing.

### Step 1 — one raw HTTP call, no SDK

A throwaway script. `httpx.post` to the Gemini REST endpoint. Print the whole response.

Read the JSON. Find `candidates`, `content.parts`, `finishReason`, `usageMetadata`. Then
deliberately break things: bad model name, malformed body, a prompt that trips a safety
filter. **The failure shapes are the thing you are learning** — every retry and fallback
you write later is a reaction to one of them.

Note especially: a `200 OK` can carry `finishReason: MAX_TOKENS` or `SAFETY` with
truncated or empty content. HTTP status is not success.

### Step 2 — the SDK, client cached

```python
# coaching/client.py
_CLIENTS: dict[str, Any] = {}

def get_client(provider: str = "gemini"):
    """Cached. NEVER construct inline.

    genai.Client().models.generate_content(...) as one expression lets the client
    be garbage-collected mid-request. It closes its httpx pool on the way out and
    the call dies with 'client has been closed'. This cost run-project real time.
    """
```

### Step 3 — first real call: journal extraction

Start here rather than with run analysis. Small input, small structured output, an
obvious schema, and easy to eval — the ideal first structured-output exercise. It is also
on the critical path, since M7 gates run analysis on a journal entry.

Force structured output with `response_mime_type="application/json"` and a
`response_schema`. Do not ask for JSON in the prompt and parse what comes back.

```python
# coaching/schemas.py — Pydantic models ARE the schema
class PainReport(BaseModel):
    location: str
    severity: int = Field(ge=1, le=5)
    when: Literal["AT_REST", "DURING_RUN", "AFTER_RUN", "STOPPED_RUN"]

class JournalFacts(BaseModel):
    applies_to_date: date       # WHICH SESSION, not which calendar day — see below
    rpe: int | None = Field(default=None, ge=1, le=10)
    energy: int | None = Field(default=None, ge=1, le=10)
    leg_fatigue: int | None = Field(default=None, ge=1, le=10)
    sleep_quality: int | None = Field(default=None, ge=1, le=10)
    pain: list[PainReport]
    fatigue_flag: bool
    illness_flag: bool
    notes_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
```

`applies_to_date` asks **which day's session an entry bears on**, not which calendar day
its words describe. Those differ, and getting it wrong is subtle. "Last night I slept
badly", written in the morning, is about *today's* session. Asked the other way, the model
answered "yesterday" — right about the words, wrong for the plan. If that field is ever
reworded, re-check this case first.

One Pydantic model used three ways: it generates the schema sent to the API, validates
what comes back, and types the rest of your code. That is the pattern to internalise.

Two traps: Gemini's schema dialect is a **subset** of JSON Schema — no `$ref`, limited
`anyOf` — so keep models flat and avoid recursion. And a schema-constrained response can
still be *semantically* wrong: valid enum, invented number. Structure is not truth, which
is why M5 exists.

### Step 4 — the context builder, where the real skill is

```python
# coaching/context.py
def athlete_state(athlete) -> dict:   # ~15 fields. State, not history.
```

The naive version sends 50 runs. It is slower, costs ~20× more, and gives *worse* answers
— the signal drowns. Send derived state, and send **run-truth numbers**, not Garmin's
blended ones:

```json
{
  "goal": "10K", "race_date": "2026-12-13", "weeks_remaining": 17,
  "phase": "FOUNDATION", "mode": "build",
  "recent_run_km_per_week": 3.2, "recent_total_km_per_week": 8.1,
  "run_fraction": 0.40, "longest_continuous_run_sec": 291,
  "run_pace": "7:05", "walk_pace": "11:20", "recent_easy_hr": 151,
  "consistency": 0.82, "rpe_trend": "stable", "limitations": []
}
```

Budget per call type and hold to it:

| Call | Context |
|---|---|
| Journal extraction | the entry + yesterday's session + today's prescription |
| Run analysis | this run + last 5–10 runs + current week + athlete state + **this run's journal** |
| Weekly review | last 4 weeks + current plan + athlete state |
| Monthly / deep | 8–12 weeks of *trend summaries*, not raw activities |

Never send the GPS polyline. Python already derived everything useful from it.

**Done:** journal extraction returns validated `JournalFacts` from a real messy entry,
then `analyze_run(activity_id)` returns a validated `RunAnalysis`. Write down both token
counts — they are the baseline every later optimisation is measured against.

---

## M5 — AI layer II: not trusting the answer

A schema-valid response can still be dangerous. This is the difference between a demo and
something you would let prescribe training to yourself.

### The chain

```
raw response → JSON parse → Pydantic → business rules → safety gate → store
```

**Business rules** — reject the plausible-but-wrong:

```python
def validate_workout(w: WorkoutGuidance, ctx: PlanContext) -> ValidationResult:
    """Reject: zero/negative distance; a next run over 1.5x the longest recent
    CONTINUOUS run; a hard session within MIN_RECOVERY_DAYS of the last; more than
    MAX_HARD_SESSIONS_PER_WEEK; a long run over MAX_LONG_RUN_PCT of weekly volume.
    Thresholds live in config, not in this file."""
```

Note `1.5x the longest recent **continuous** run`. Against total logged distance the same
rule would wave through a 3.75 km continuous run for someone whose longest unbroken block
is 4:51.

**Safety gate — runs BEFORE the model, not after.** If the journal reported pain, injury,
chest pain, dizziness or unusual breathlessness, the model is **never asked** to generate
a harder session. A gate that only filters output is one you have already walked through.

> The model **proposes**. Your code **approves**. Nothing an LLM returns reaches the
> athlete without passing deterministic rules it cannot influence.

Journal facts drive this deterministically: fatigue → shorten, pain → no progression,
illness → drop the session. All Python. That is what keeps the "only ever easier"
guarantee somewhere a hallucination cannot reach, and it means a bad extraction produces
a wrong *fact the athlete can see and correct*, not a wrong prescription.

### Caching

```python
input_hash = sha256(canonical_json(context) + prompt_version + model)
```

Same input, same prompt version, same model → return the stored analysis. During
development you will re-run the same analysis constantly.

### Cost logging

`AIRequestLog`: `model`, `operation`, `prompt_version`, `input_tokens`, `output_tokens`,
`latency_ms`, `estimated_cost`, `status`, `retry_count`, `error`.

Write it on **every** call including failures — failed calls are billed too. Take token
counts from `usageMetadata`, never from string length: **thinking tokens bill as output
and do not appear in the text you read.** See [COST.md](COST.md).

**Done:** a pain-flagged journal entry demonstrably cannot produce a harder session, and
that is a *test*, not something checked once by hand. A second identical analysis costs
zero tokens. The log table shows real per-run cost.

---

## M6 — AI layer III: failure, swappability, evaluation

### Reliability ladder

```
coach model → cheaper model → deterministic fallback planner
```

The athlete is never left without a workout because an API was down. The fallback repeats
the approved plan, downgrades on a fatigue flag, refuses progression on an injury flag,
and **never compresses missed workouts** into the following week.

Handle distinctly: timeout, 429, 5xx, malformed JSON, schema-valid-but-rule-rejected.
Exponential backoff with jitter. Rate limits get their own status and are **retried later,
not written off** — a spent quota is a wait, not a failure.

### Provider abstraction

```python
class CoachProvider(Protocol):
    def generate(self, prompt: str, schema: type[BaseModel], tier: str) -> BaseModel: ...
```

Implement Gemini, then implement Claude — not for redundancy, **as a test of the seam**.
If the second provider forces changes outside `providers/`, the abstraction leaked and you
found out now rather than at the migration.

Tiers stay in env, mapped per operation:

```python
MODEL_TIERS = {
    "journal_extract": "lite", "run_analysis": "fast", "weekly_review": "coach",
    "plan_generation": "coach", "monthly_review": "deep", "summary": "lite",
}
```

### Eval harness — the part most people skip

30–50 fixtures: clean easy run, badly paced, high HR in heat, hilly, **run/walk with long
breaks and a low run fraction**, a missed week, rapid progression, a pain report, a
sensor-glitch activity, a run with no HR at all, and journal entries that are terse,
rambling, and code-switched Hindi/English.

Assert on **structure and safety, never prose**:

- Valid JSON matching the schema — always.
- No invented numbers. Every figure traces to an input field.
- No unsafe progression on any fatigue or pain fixture.
- Missing data acknowledged as missing, not filled in.
- `applies_to_date` correct on the "last night I slept badly" case.

Run on every prompt change. **Never edit a prompt silently** — bump `prompt_version`,
re-run evals, compare. It is the only way to know an edit improved anything.

**Done:** evals pass on both providers. Killing the network mid-week still yields a
workout. Prompt v1 vs v2 is a diff you can read.

---

## M7 — Pipelines · Celery

```
sync_garmin → segment → calculate_metrics → [WAIT FOR JOURNAL] → analyze_run
weekly (Sunday): aggregate → weekly_review → replan → validate → store
```

**The journal gate.** An activity lands as `PENDING_JOURNAL`. Metrics compute immediately
— they need no subjective input — but run analysis does not fire until a journal entry
exists. Deliberate: the subjective read is the highest-value input and the only one Garmin
cannot supply.

An escape hatch exists so a forgotten entry cannot deadlock the pipeline forever: "skip
with reason" marks the activity analysable with `subjective_data: missing`, and the
analysis says so rather than quietly proceeding as though nothing were absent.

Queue separation (`garmin`, `metrics`, `ai`, `planning`) matters: a stuck AI call must not
block the next Garmin sync.

**Idempotent throughout.** Celery will re-run tasks, at the worst moment, and a task that
double-writes turns a retry into corruption. A sweep task heals rate-limited rows on beat,
with nobody watching.

**Done:** a real activity lands, is journalled from the phone, and produces a stored
analysis with no manual step.

---

## M8 — Adaptive planning

Weekly classification from actual data: `ON_TRACK` · `UNDER_LOADED` · `OVER_LOADED` ·
`FATIGUED` · `RECOVERING` · `ANOMALOUS`. Deterministic rules first; the model interprets
the classification rather than making it.

Then regenerate remaining `build` weeks from current state — new `generation`, previous
retained. The plan is a live projection, not a document written once. The prediction
range (M3b) refreshes alongside and should visibly narrow.

**The athlete approves changes.** A plan that silently rewrites itself is one you stop
trusting, and correctly so.

**Done:** a deliberately terrible week visibly reduces next week's load. A week with
logged pain produces no progression at all. Two generations of the same future week can be
diffed in the UI.

---

## M9 — Frontend + PWA · *Claude*

Runs in parallel from M2 onward against whatever endpoints exist.

**Today** — the session and why it exists · **This week** — planned vs actual ·
**Run detail** — blocks, splits, HR, cadence, the analysis · **Journal** — the mandatory
post-run form, prominent and hard to ignore · **Progress** — longest continuous block over
time as the hero chart · **Prediction** — range with its confidence and what would move it
· **Plan** — timeline, phases, races, generation diffs.

Two display rules:

- **Run truth is the headline number.** `1.0 km run · 1.5 km walk` before, or instead of,
  `2.5 km`. The blended figure is the one that has been misleading all along.
- **Indicators, never fabricated percentages.** `10K readiness: Developing`, not
  `73.42%`. Prediction shows as a range; under the M3b gate it shows nothing at all.

PWA: manifest, service worker, offline shell, installable. Android/Chrome prompts to
install; iOS requires Safari's Share → Add to Home Screen. The UI detects which and says
the right thing rather than showing an Android prompt to an iPhone.

---

## Sequencing

```
M0 → M1 → M2 → M3a → M3c → M4 → M5 → M6 → M7 → M8
              └→ M3b ↗
         └────────── M9 frontend, continuous ──────────┘
```

M3a before M3c — the generator only fills days the resolver marked `build`. M3b can be
built any time after M2 but stays useless until there is history to fit.

M4 needs M2's segmented metrics to have something real to interpret. Starting the AI layer
against fake data teaches the wrong lessons about context size.

## Working rhythm

Claude specs a module → Rohit implements → Claude reviews against the done-tests →
`CONTEXT.md` gets updated → next module.

Ask for the spec one module at a time. A spec for M5 written before M4 exists is a guess
about code that does not exist yet.
