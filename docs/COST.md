# What this will cost to run

Recomputed 2026-08-19 against published OpenAI rates. Redo this if the call mix changes.

**Provider: OpenAI.** Google Cloud billing requires a billing account with auto-charge,
which failed here — a common outcome for Indian cards, since RBI e-mandate rules make
banks decline recurring-charge authorisations. OpenAI sells **prepaid credits** instead:
one card charge, drawn down by usage, no recurring mandate. That mechanism difference is
why the project is on OpenAI, not a judgement about the models.

Current balance: **$5**, added as API credit (not a ChatGPT subscription — those are
separate products and a subscription grants no API access).

## Expected monthly call volume

Assumes ~4 runs/week, a mandatory journal entry after every run plus most rest days, and
occasional coach questions.

| Operation | Tier | Calls/mo | Input | Output |
|---|---|---:|---:|---:|
| Journal extraction | fast | 40 | 800 | 300 |
| Run analysis | fast | 17 | 2,500 | 800 |
| Weekly review + next week | coach | 4.3 | 5,000 | 1,500 |
| Monthly deep review | deep | 1 | 15,000 | 3,000 |
| Coach chat | coach | 30 | 3,000 | 600 |
| Prediction refresh | fast | 4 | 2,000 | 500 |
| **Total** | | **~96** | **~210k** | **~55k** |

Small, because the context builder sends ~15 derived fields rather than 50 raw
activities. The naive design is roughly 20× this and gives worse answers.

## Cost

Rates as of August 2026, per million tokens.

| Model | In | Out | Cached in | ₹/mo @ ₹88 | $5 lasts |
|---|---:|---:|---:|---:|---|
| GPT-5 nano | 0.05 | 0.40 | 0.025 | ₹3 | ~13 years |
| GPT-5.6 Luna | 0.20 | 1.20 | 0.02 | ₹10 | ~4 years |
| **GPT-5.6 Terra** | **2.00** | **12.00** | **0.20** | **₹95** | **~4.5 months** |
| GPT-5.6 Sol | 5.00 | 30.00 | 0.50 | ₹238 | ~7 weeks |

**Running on Terra.** Every call repeats the same system prompt and athlete state, so
prompt caching at 10% of standard input rates should pull the real figure nearer ₹75 —
worth wiring up at M5 alongside the `input_hash` cache.

## The spike to watch: eval runs at M6

Steady-state traffic is not what will drain the balance. The eval suite is.

A full 40-fixture run costs roughly **$0.58 on Terra** — about ~100k input and ~32k
output. Re-running it on every prompt version bump, which is exactly the discipline M6
asks for, gets expensive fast: eight full runs is the whole $5.

**Run eval iteration on `gpt-5.6-luna` (~$0.06 per full run, 10× cheaper), and validate
the final prompt version on Terra.** Structural assertions — valid JSON, no invented
numbers, no unsafe progression on a pain fixture — are mostly model-independent, so the
cheap model catches the majority of regressions. Save Terra for confirming the prompt you
intend to ship.

Budget roughly: **$5 covers ~4 months of normal use, or ~2 months if M6 lands in the
middle of it.** Top up when the balance drops below $2 rather than when it hits zero — a
dead balance mid-week means no coaching, and the deterministic fallback planner is a
safety net, not a substitute.

## The one thing that could break this estimate

**Reasoning tokens bill as output.** A reasoning model can emit several times more
internal thinking than visible text, and none of it appears in the response you read. If
Terra reasons by default, budget its output at 3–5× the visible length.

Check this on the very first raw HTTP call at M4 — compare reported output tokens against
the visible response length. If they diverge sharply, this whole table needs revising,
and finding that out on call one beats finding it out when the balance is gone.

This is why `AIRequestLog` records real token counts from the API response rather than
estimating from string lengths.

## Controls to set now

- **A usage limit** in the OpenAI dashboard. Prepaid credit caps the downside already,
  but a hard limit stops a runaway Celery retry loop burning the balance overnight.
- **`AIRequestLog` from M5**, so per-operation cost is visible before it is surprising.

## Sources

- [OpenAI API Pricing (August 2026) — BenchLM](https://benchlm.ai/openai/api-pricing)
- [OpenAI API pricing in 2026 — CloudZero](https://www.cloudzero.com/blog/openai-pricing/)
