# Hosting this publicly — what changes

Written 2026-08-19, when the decision was made to allow public registration.

Going from "one athlete on a laptop" to "anyone can sign up" changes three things
structurally. None of them blocks building. All of them are cheaper to design for now
than to retrofit.

---

## 1. Every user costs you money

The ₹95/month in [COST.md](COST.md) is **for one athlete**. It scales linearly with
registrations, and your balance is $5 of prepaid credit.

| Registered users | Cost/month | $5 lasts |
|---:|---:|---|
| 1 | ₹95 | ~4.5 months |
| 10 | ₹950 | ~2 weeks |
| 50 | ₹4,750 | ~3 days |
| 200 | ₹19,000 | ~18 hours |

There is no natural ceiling. A post that does modestly well somewhere could drain the
balance overnight, and the failure mode is every existing user's coaching silently
stopping.

### Controls, cheapest first

**A per-user AI budget, enforced in the coaching service.** This is the one that matters.
Count calls from `AIRequestLog` for the current month and refuse past the cap, falling
back to the deterministic planner. M5 builds that fallback anyway — it exists so an API
outage never leaves an athlete without a workout, and a spent budget is the same
situation. The `"ai": "30/day"` throttle in M1a is the crude version of this; the real one
is monthly and per-operation.

**Invite codes.** A `signup_code` field checked at registration keeps growth deliberate
while the economics are unproven. Trivial to add now, awkward once people are signing up.

> **Deliberately not doing this yet** (2026-08-19). Registration is open. Current users
> are Rohit and a couple of friends, so the unbounded-cost risk is theoretical, and a
> hard spend limit in the OpenAI dashboard is enough backstop. Revisit if signups arrive
> from people you did not tell about it.

**A hard spend limit in the OpenAI dashboard.** The backstop for everything above. Set it.

**Bring-your-own-key.** The end state if this ever grows: each athlete supplies their own
OpenAI key, stored encrypted. Costs move to the user and scale stops being your problem.
Worth designing the provider layer so this is possible — the M6 abstraction already takes
the key per-call rather than reading it globally, or should.

**Do not** launch open registration with no cap and watch the balance. That is not a
plan, and users lose coaching mid-training-block when it runs out.

---

## 2. Garmin rate-limits by IP, and you have one

Every athlete's sync leaves from your single server IP. Garmin's unofficial endpoints
throttle aggressively per source address — `run-project` already hit "Garmin rate-limited
this network", and that was one user.

With N users this is not a tail risk, it is the normal case. Ten athletes syncing after
their morning runs are ten bursts of activity downloads from one IP inside an hour.

### What follows

- **Serialise Garmin work.** A dedicated Celery queue with **concurrency 1** and a
  deliberate delay between athletes. Parallel syncing is precisely what triggers the
  block, and a block affects *everyone*, not just the athlete who caused it.
- **Stagger the schedule.** Do not sync every athlete at 06:00. Spread them across the
  hour by athlete id.
- **Treat 429 as a global circuit breaker.** When Garmin rate-limits, stop the whole queue
  for a back-off window rather than continuing to the next athlete — the limit is on the
  IP, so continuing makes it worse and lengthens the block.
- **Make it visible.** An athlete whose sync is delayed by someone else's should see
  "sync delayed", not stale data presented as current.

`run-project`'s `garmin.py` already classifies 429 distinctly. That classification becomes
load-bearing here rather than a nicety.

**Also worth knowing:** Garmin has no personal API and the Developer Program requires a
legal entity, rejects personal use, and is on hold. Running an unofficial client on
behalf of *other people* is a materially different proposition from running it for
yourself — both in what Garmin's terms allow and in what breaks when they change
something. Worth deciding deliberately rather than by default.

---

## 3. You are holding other people's health data

Sleep, injuries, pain, alcohol, mood, and GPS traces that start at their home. Plus,
briefly, their Garmin password during the connect flow.

That was your own data before. It is not now.

### Non-negotiable before the first external user

- **HTTPS everywhere.** `garmin_connect.py`'s docstring says it plainly: passing a
  password over localhost is fine, over a real domain it must be TLS-only. Set
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`,
  and `SECURE_HSTS_SECONDS`.
- **`DEBUG=0` and a real `SECRET_KEY`** from the environment. `DEBUG=1` on a public host
  renders a full traceback with settings values on any 500.
- **`ALLOWED_HOSTS` set to your actual domain**, not `*`.
- **`AthleteScopedMixin` on every single view.** With one user a missed filter is
  invisible. With many it is a breach, and it produces no error and no log line.
- **The password stays untouched.** `garmin_connect.py` never persists, logs, or echoes
  it. Do not add a "remember my Garmin login" convenience.
- **Never log request bodies** on auth or Garmin endpoints.

### Worth doing early

- **Account deletion that actually deletes** — `RawFitFile` bytes, records, tokens, the
  lot. Easier to build now than to bolt on when someone asks for it.
- **A plain-language note at registration** saying what is stored, that entries go to
  OpenAI for analysis, and that OpenAI does not train on API data. People logging
  injuries deserve to know where it goes.
- **Per-athlete token directories** — already in the `Athlete.token_dir` design. Never
  share a Garmin session between athletes.

---

## What this means for the roadmap

Nothing is reordered. Three things get added:

- **M1a** — throttling on the public endpoints. Already in the spec.
- **M5** — the AI budget check sits alongside the safety gate, and both run *before* the
  model is called.
- **Before launch** — a hardening pass: the settings above, account deletion, and the
  Garmin queue serialisation.

The single-user version works fine with none of it. Do not let this list stall M1a — just
do not launch without it.
