# What this will cost to run

Recomputed 2026-08-19 against published Gemini rates. Redo this if the call mix changes.

## Expected monthly call volume

Assumes ~4 runs/week, a mandatory journal entry after every run plus most rest days,
and occasional coach questions.

| Operation | Tier | Calls/mo | Input | Output |
|---|---|---:|---:|---:|
| Journal extraction | lite | 40 | 800 | 300 |
| Run analysis | fast | 17 | 2,500 | 800 |
| Weekly review + next week | coach | 4.3 | 5,000 | 1,500 |
| Monthly deep review | deep | 1 | 15,000 | 3,000 |
| Coach chat | coach | 30 | 3,000 | 600 |
| Prediction refresh | fast | 4 | 2,000 | 500 |
| **Total** | | **~96** | **~210k** | **~55k** |

Small, because the context builder sends ~15 derived fields instead of 50 raw activities.
The naive design — dump recent runs into the prompt — is roughly 20× this, and gives
worse answers.

## Cost

Rates as of August 2026. Gemini 3.7 Flash is $0.75 / $3.75 per million tokens (in/out),
rising to $1.50 / $7.50 on 1 January 2027. Gemini 3.1 Flash-Lite is $0.25 / $1.50.

| Scenario | USD/mo | INR/mo @ ₹88 |
|---|---:|---:|
| Everything on Flash, current rates | $0.36 | **₹32** |
| Tiered (lite for journal), current | $0.32 | **₹28** |
| Everything on Flash, post-Jan-2027 | $0.73 | **₹64** |
| 3× the assumed volume, post-Jan-2027 | $2.19 | **₹193** |

Response caching on `input_hash` (M5) removes re-analysis of unchanged runs entirely,
which during development is most of the traffic.

## Conclusion

**Go paid from day one.** At ₹30–65/month the free tier saves nothing worth having, and
free-tier content is used to improve Google's products. What gets logged here is sleep,
alcohol, injuries, pain and mood. That is not a trade worth ₹40.

Even a 5× error in these volume assumptions leaves the monthly bill under ₹350.

## The one thing that could break this estimate

**Thinking tokens are billed as output.** A reasoning model can emit several times more
internal thinking than visible text, and it does not appear in the response you read. If
the deep monthly review uses a thinking model, budget its output at 3–5× the visible
length, and check `usageMetadata` rather than assuming.

This is exactly why `AIRequestLog` records real token counts from the API response
instead of estimating from string lengths.

## Sources

- [Gemini API Pricing (August 2026) — BenchLM](https://benchlm.ai/google/api-pricing)
- [Gemini pricing in 2026 — CloudZero](https://www.cloudzero.com/blog/gemini-pricing/)
- [Gemini API Pricing Calculator & Cost Guide (Aug 2026) — CostGoat](https://costgoat.com/pricing/gemini-api)
