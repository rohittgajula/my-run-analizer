# AI Running Coach — Gemini-Powered 17-Week 10K Training System

## 1. Project goal

Build a personal running-coach system around Garmin data that helps an athlete complete a 10K in 17 weeks.

The system should:

- Import Garmin activities and health/training data.
- Store a clean historical training record.
- Calculate deterministic running metrics in Python.
- Use Gemini APIs for interpretation, coaching, summaries, and adaptive planning.
- Generate a 17-week baseline plan, then adapt it based on actual training.
- Analyze every completed run.
- Produce a weekly training review.
- Recommend the next week's workouts.
- Track progress toward 10K completion.
- Avoid unsafe/aggressive recommendations.
- Keep AI responsible for interpretation, not arithmetic.

Primary principle:

> Python calculates. Gemini interprets and coaches.

---

# 2. Recommended architecture

```text
                         Garmin
                           |
                           | Activities / HR / GPS / cadence
                           v
                  Garmin ingestion layer
                           |
                           v
                    Django REST API
                           |
             +-------------+-------------+
             |                           |
             v                           v
       PostgreSQL                    Redis
       Training DB              cache / jobs
             |                           |
             +-------------+-------------+
                           |
                           v
                   Metrics Engine
                     (Python)
                           |
             +-------------+-------------+
             |                           |
             v                           v
       Run Analyzer                 Plan Engine
                           |
                           v
                    Gemini API layer
                           |
             +-------------+-------------+
             |                           |
             v                           v
       Run analysis               Weekly review
             |                           |
             +-------------+-------------+
                           |
                           v
                    Adaptive Plan
                           |
                           v
                    User dashboard
```

Recommended stack:

- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery
- Gemini API
- Garmin data integration
- Docker
- Optional: Prometheus + Grafana
- Optional frontend/mobile client later

---

# 3. AI model strategy

Use Gemini as the AI layer, but do not use the most expensive model for every operation.

Recommended tiers:

### Gemini Flash-Lite

Use for:

- Simple classification
- Tagging
- Short summaries
- Extracting structured information
- Low-cost repeated operations

### Gemini Flash

Use as the primary coach for:

- Run analysis
- Workout analysis
- Weekly reviews
- Training adjustments
- Structured training recommendations

### Higher-end Gemini reasoning model

Use selectively for:

- 4-week or 8-week progress reviews
- Major plan changes
- Difficult tradeoff analysis
- Long-context analysis of historical training
- Investigating unusual performance trends

The exact Gemini model IDs should be configurable through environment variables so models can be upgraded without changing application code.

Example:

```env
GEMINI_FAST_MODEL=gemini-...
GEMINI_COACH_MODEL=gemini-...
GEMINI_DEEP_MODEL=gemini-...
```

Do not hard-code model names throughout the codebase.

---

# 4. Core design principle

Do NOT send raw Garmin data directly to Gemini and ask it to calculate everything.

Bad:

```text
Here are 50 runs.
Calculate my training load, pace trends, HR drift,
cadence trends and create a plan.
```

Better:

```text
Garmin
  ↓
Python calculations
  ↓
Normalized metrics
  ↓
Gemini
  ↓
Interpretation
  ↓
Structured recommendation
```

For example:

```json
{
  "distance_km": 4.21,
  "moving_time_sec": 1898,
  "avg_pace_sec_per_km": 451,
  "avg_hr": 154,
  "max_hr": 172,
  "avg_cadence": 162,
  "elevation_gain_m": 31,
  "hr_drift_percent": 7.2,
  "pace_variability_percent": 5.1,
  "walk_breaks": 3,
  "weekly_distance_km": 13.4,
  "longest_run_km": 5.2
}
```

Gemini interprets those numbers.

---

# 5. Major components

## 5.1 Garmin ingestion service

Responsibilities:

- Authenticate with Garmin.
- Fetch new activities.
- Detect duplicate activities.
- Normalize Garmin data.
- Store raw activity payload if useful.
- Store normalized activity data.
- Queue metric calculation.
- Queue AI analysis.

Recommended flow:

```text
Garmin
  ↓
Sync command / scheduled job
  ↓
Fetch activities after last_sync
  ↓
Deduplicate
  ↓
Normalize
  ↓
Store Run
  ↓
Calculate Metrics
  ↓
Run AI Analysis
```

Use Celery for background processing.

Example:

```text
garmin_sync
    ↓
calculate_run_metrics
    ↓
analyze_run_with_gemini
```

---

# 6. Database design

Use PostgreSQL.

## 6.1 AthleteProfile

```text
AthleteProfile
-------------------------
id
name
age
height_cm
weight_kg
experience_level
goal_type
goal_distance_km
goal_date
goal_priority
current_fitness_notes
created_at
updated_at
```

Do not store unnecessary sensitive information.

---

## 6.2 TrainingGoal

```text
TrainingGoal
-------------------------
id
athlete_id
name
distance_km
target_date
weeks
priority
target_type
status
created_at
updated_at
```

Example:

```text
10K completion
17 weeks
No time target
Primary objective: finish safely
```

---

## 6.3 TrainingWeek

```text
TrainingWeek
-------------------------
id
goal_id
week_number
start_date
end_date
phase
planned_distance_km
actual_distance_km
status
ai_summary
created_at
updated_at
```

Phases:

```text
Foundation
Aerobic Development
10K Development
Peak
Taper
Race
```

---

## 6.4 Workout

```text
Workout
-------------------------
id
training_week_id
date
workout_type
planned_duration_min
planned_distance_km
target_effort
target_pace_low
target_pace_high
target_hr_low
target_hr_high
instructions
status
completed_activity_id
created_at
updated_at
```

Workout types:

```text
REST
EASY
LONG_EASY
RUN_WALK
INTERVAL
TEMPO
PROGRESSION
RECOVERY
RACE
CROSS_TRAINING
```

Do not make every week interval-heavy.

---

## 6.5 RunActivity

```text
RunActivity
-------------------------
id
garmin_activity_id
start_time
duration_sec
moving_time_sec
distance_m
avg_pace_sec_per_km
avg_hr
max_hr
avg_cadence
max_cadence
elevation_gain_m
elevation_loss_m
calories
training_effect
raw_payload
created_at
updated_at
```

---

## 6.6 RunSplit

```text
RunSplit
-------------------------
id
activity_id
split_number
distance_m
duration_sec
pace_sec_per_km
avg_hr
avg_cadence
elevation_gain_m
```

---

## 6.7 RunMetrics

Calculated by Python.

```text
RunMetrics
-------------------------
activity_id
pace_consistency
hr_drift_percent
cadence_consistency
first_half_pace
second_half_pace
first_half_hr
second_half_hr
negative_split
walk_break_count
effort_score
aerobic_efficiency_proxy
load_score
recovery_need_score
anomaly_flags
calculated_at
```

Important:

Metrics that require medical-grade interpretation should be explicitly labeled as estimates.

---

## 6.8 AIAnalysis

```text
AIAnalysis
-------------------------
id
activity_id
model
prompt_version
input_hash
analysis_type
result_json
created_at
```

Analysis types:

```text
RUN
WEEKLY
MONTHLY
PLAN
PROGRESS
ANOMALY
```

Store prompt versions.

---

## 6.9 TrainingRecommendation

```text
TrainingRecommendation
-------------------------
id
training_week_id
source
recommendation_json
confidence
accepted
created_at
```

Source:

```text
AI
RULE
HYBRID
```

---

# 7. Metrics engine

This is one of the most important parts of the system.

Create a Python package:

```text
metrics/
    __init__.py
    pace.py
    heart_rate.py
    cadence.py
    splits.py
    load.py
    consistency.py
    recovery.py
    trends.py
```

## Pace metrics

Calculate:

- Average pace
- Moving pace
- Best kilometer
- Slowest kilometer
- Pace standard deviation
- First-half pace
- Second-half pace
- Negative/positive split
- Pace drift

---

# 8. Heart-rate analysis

Calculate:

- Average HR
- Maximum HR
- HR per kilometer
- HR relative to pace
- First-half HR
- Second-half HR
- HR drift

Example:

```text
HR drift =
(second-half average HR - first-half average HR)
/
first-half average HR
× 100
```

Interpret carefully.

A high HR drift can be influenced by:

- heat
- humidity
- hills
- dehydration
- fatigue
- sensor error
- insufficient aerobic conditioning

Do not automatically interpret it as poor fitness.

---

# 9. Cadence analysis

Calculate:

- Average cadence
- Cadence per split
- Cadence variability
- Cadence vs pace relationship

Do NOT enforce a universal cadence target such as 180 spm.

Gemini should evaluate cadence in context.

Example:

```text
pace: 7:30/km
cadence: 162

pace: 6:45/km
cadence: 166
```

That trend can be more useful than an arbitrary target.

---

# 10. Training load

Build a simple transparent load model first.

Example:

```text
session_load =
duration_minutes × effort_factor
```

Then calculate:

```text
daily_load
weekly_load
rolling_7_day_load
rolling_28_day_load
```

Do not pretend this is equivalent to Garmin's proprietary training load.

Call it:

```text
Custom Training Load
```

Keep the formula versioned.

Example:

```text
load_formula_version = "v1"
```

Later you can experiment with:

- HR-based TRIMP
- session RPE
- duration × RPE
- pace-based load
- combined load

---

# 11. Easy vs hard distribution

Classify workouts:

```text
RECOVERY
EASY
MODERATE
HARD
```

Use deterministic rules first.

Then let Gemini interpret whether the overall distribution looks appropriate.

The AI should not arbitrarily turn an easy run into a hard workout.

---

# 12. Training phases

The 17-week plan should have phases.

A reasonable baseline:

```text
Weeks 1–4
Foundation

Weeks 5–8
Aerobic development

Weeks 9–13
10K development

Weeks 14–15
Peak

Week 16
Taper

Week 17
Race
```

This is only the starting framework.

Actual progression must adapt to the athlete's performance and recovery.

---

# 13. Baseline 17-week plan

The system should generate a baseline plan.

Example structure:

## Weeks 1–4 — Foundation

Main goal:

- Establish consistency
- Increase time spent running
- Introduce controlled run/walk
- Build easy aerobic volume

Typical week:

```text
Day 1: Rest
Day 2: Easy run
Day 3: Rest / cross training
Day 4: Easy run
Day 5: Rest
Day 6: Easy or short progression
Day 7: Long easy / run-walk
```

Do not prescribe exact paces until sufficient data exists.

---

## Weeks 5–8 — Aerobic development

Main goals:

- Longer continuous running
- Gradually extend long run
- Introduce small amounts of structured faster running
- Maintain mostly easy running

Example:

```text
Easy
Easy
Rest
Light intervals / progression
Rest
Easy
Long easy
```

---

## Weeks 9–13 — 10K development

Main goals:

- Improve endurance
- Increase long-run duration
- Introduce controlled tempo/interval work
- Practice sustained running

The AI should select workouts based on observed fitness.

---

## Weeks 14–15 — Peak

Main goals:

- Reach strong long-run duration
- Practice race-relevant effort
- Avoid unnecessary fatigue

Do not maximize weekly mileage just because the race is approaching.

---

## Week 16 — Taper

Reduce volume.

Maintain some intensity.

Avoid introducing new workouts.

---

## Week 17 — Race

Reduce training.

Prioritize:

- recovery
- sleep
- nutrition
- hydration
- confidence
- race execution

---

# 14. Adaptive training logic

The system should NOT blindly follow the baseline plan.

Each week evaluate:

```text
planned workload
actual workload
completion rate
longest run
average easy pace
HR trends
fatigue signals
missed workouts
pain/injury flags
sleep/recovery data if available
```

Then classify the week:

```text
ON_TRACK
UNDER_LOADED
OVER_LOADED
FATIGUED
RECOVERING
ANOMALOUS
```

---

# 15. Adjustment rules

Use a hybrid approach.

## Deterministic safety rules

Examples:

```text
IF pain_flag == true:
    do not increase training load
```

```text
IF previous_week_load increased significantly
AND recovery indicators are poor:
    reduce next week's load
```

```text
IF athlete missed several workouts:
    do not automatically compress missed workouts
```

```text
IF long run was substantially harder than expected:
    consider recovery before next hard session
```

The exact thresholds should be configurable.

---

# 16. Gemini's role

Gemini should answer:

```text
What happened?

Why might it have happened?

Is it meaningful?

What should change?

What should NOT change?

What should the athlete do next?
```

Gemini should NOT decide:

```text
distance = 7.3 km
```

based on arithmetic.

Python calculates that.

---

# 17. Gemini prompt architecture

Use layered prompts.

## System prompt

```text
You are an evidence-based recreational endurance running coach.

Your job is to analyze training data and provide conservative,
practical recommendations for a beginner training toward a 10K.

Priorities:

1. Consistency
2. Injury risk reduction
3. Appropriate recovery
4. Aerobic development
5. Gradual progression
6. Race-specific preparation

Do not invent data.

If data is insufficient, explicitly say so.

Do not diagnose medical conditions.

Do not prescribe medical treatment.

Do not assume that a single run represents fitness.

Consider environmental factors, terrain, fatigue and measurement error.

Distinguish:
- observed facts
- likely interpretation
- recommendation

Return the requested JSON schema exactly.
```

---

# 18. Run analysis prompt

Send:

```json
{
  "athlete": {
    "goal": "Complete 10K",
    "weeks_remaining": 13
  },
  "current_plan": {...},
  "run": {...},
  "metrics": {...},
  "recent_runs": [...]
}
```

Ask Gemini to return:

```json
{
  "summary": "",
  "what_went_well": [],
  "observations": [],
  "possible_explanations": [],
  "concerns": [],
  "recovery_recommendation": {
    "level": "LOW",
    "reason": ""
  },
  "next_workout_guidance": {
    "type": "",
    "duration_min": null,
    "distance_km": null,
    "effort": "",
    "instructions": ""
  },
  "training_adjustment": {
    "change_required": false,
    "reason": ""
  },
  "confidence": 0.0
}
```

---

# 19. Weekly review prompt

Every week send:

```text
Goal
Current week
Previous 4 weeks
Planned workouts
Completed workouts
Metrics
Recovery data
User notes
```

Ask:

```text
1. Assess training consistency.
2. Assess aerobic progression.
3. Assess workload progression.
4. Identify fatigue signals.
5. Identify positive trends.
6. Identify negative trends.
7. Decide whether the current plan should change.
8. Create next week's workouts.
9. Explain why each workout exists.
```

---

# 20. Weekly output schema

```json
{
  "week_assessment": {
    "status": "ON_TRACK",
    "score": 0,
    "summary": ""
  },
  "progress": {
    "endurance": "",
    "pace": "",
    "heart_rate": "",
    "cadence": "",
    "consistency": ""
  },
  "risks": [],
  "next_week": {
    "focus": "",
    "planned_runs": [],
    "target_volume_km": null
  },
  "plan_changes": [],
  "confidence": 0.0
}
```

---

# 21. Workout generation

Each workout should be structured.

Example:

```json
{
  "type": "EASY",
  "duration_min": 35,
  "effort": "Very easy to easy",
  "pace_guidance": "Conversational; do not chase pace",
  "hr_guidance": null,
  "warmup": null,
  "main": "30 minutes easy running",
  "cooldown": "5 minutes easy walk",
  "purpose": "Aerobic development and recovery"
}
```

For intervals:

```json
{
  "type": "INTERVAL",
  "warmup": "10 minutes easy",
  "main": "4 × 3 minutes controlled hard",
  "recovery": "2 minutes easy between repetitions",
  "cooldown": "10 minutes easy",
  "purpose": "Introduce controlled faster running"
}
```

---

# 22. User feedback loop

After each workout allow the athlete to enter:

```text
How did it feel?
RPE: 1–10
Any pain?
Energy: 1–10
Leg fatigue: 1–10
Sleep quality: 1–10
Weather:
Surface:
Notes:
```

This data can be more useful than blindly relying on Garmin metrics.

---

# 23. Pain/injury safety layer

Create a hard safety gate BEFORE Gemini plan generation.

Example:

```text
pain_reported
injury_reported
chest_pain
dizziness
fainting
unusual_shortness_of_breath
```

If serious symptoms are reported:

```text
Do not generate a harder workout.
Flag for professional medical evaluation.
```

Gemini should never be the sole medical decision-maker.

---

# 24. Environmental context

If available, capture:

```text
temperature
humidity
wind
elevation
surface
time_of_day
```

This matters especially for running in hot/humid conditions.

A slower pace at the same effort does not necessarily mean worse fitness.

---

# 25. AI API service

Create:

```text
services/
    gemini/
        client.py
        models.py
        prompts.py
        schemas.py
        analyzer.py
        planner.py
        exceptions.py
```

Example architecture:

```python
class GeminiCoach:
    def analyze_run(self, context):
        ...

    def review_week(self, context):
        ...

    def generate_plan(self, context):
        ...

    def analyze_progress(self, context):
        ...
```

Keep Gemini-specific code isolated.

---

# 26. Prompt versioning

Never silently change prompts.

Store:

```text
prompt_name
prompt_version
model
temperature/config
input_hash
created_at
```

Example:

```text
run_analysis_v1
run_analysis_v2
weekly_review_v1
```

This lets you compare AI behavior.

---

# 27. AI response validation

Never trust model output blindly.

Flow:

```text
Gemini response
      ↓
JSON parse
      ↓
Pydantic validation
      ↓
Business-rule validation
      ↓
Safety validation
      ↓
Store
```

Example:

```python
RunAnalysisResponse.model_validate(response)
```

Reject:

- missing fields
- invalid enum values
- negative distances
- impossible durations
- malformed workouts

---

# 28. Recommendation validator

Before accepting an AI plan:

```text
AI recommendation
        ↓
Safety rules
        ↓
Load progression rules
        ↓
Workout conflict checks
        ↓
Calendar checks
        ↓
Accept / modify / reject
```

The AI should propose.

Your application should approve.

---

# 29. Example safety rules

Make these configurable rather than hard-coding arbitrary numbers.

Examples:

```text
MAX_WEEKLY_VOLUME_INCREASE
MAX_HARD_SESSIONS_PER_WEEK
MIN_RECOVERY_DAYS_AFTER_HARD_SESSION
MAX_LONG_RUN_PERCENT_OF_WEEKLY_VOLUME
TAPER_START_WEEK
```

The exact values should be chosen conservatively and reviewed rather than treated as universal laws.

---

# 30. Celery architecture

Recommended tasks:

```text
sync_garmin_activities
calculate_activity_metrics
analyze_activity
generate_weekly_review
generate_next_week_plan
calculate_training_trends
detect_training_anomalies
```

Queues:

```text
garmin
metrics
ai
planning
```

Example:

```text
garmin queue
    ↓
metrics queue
    ↓
ai queue
```

Weekly:

```text
generate_weekly_review
    ↓
generate_next_week_plan
```

---

# 31. Redis

Use Redis for:

- Celery broker
- Temporary AI request state
- API rate limiting
- Caching recent summaries
- Idempotency locks

Do not use Redis as the permanent training database.

---

# 32. API endpoints

Example Django REST API:

```text
GET    /api/runs/
GET    /api/runs/{id}/
GET    /api/runs/{id}/analysis/
POST   /api/runs/{id}/reanalyze/

GET    /api/training-plan/
GET    /api/training-plan/current-week/
GET    /api/workouts/upcoming/
POST   /api/workouts/{id}/feedback/

GET    /api/progress/
GET    /api/progress/weekly/
GET    /api/progress/trends/

POST   /api/garmin/sync/

GET    /api/coach/weekly-review/
POST   /api/coach/ask/
```

---

# 33. Garmin synchronization

Use an abstraction:

```python
class ActivityProvider:
    def get_activities(self, after=None):
        raise NotImplementedError
```

Then:

```python
class GarminActivityProvider(ActivityProvider):
    ...
```

This keeps the rest of the application independent of Garmin.

If Garmin access changes later, you replace the provider rather than rewriting the system.

---

# 34. Idempotency

Garmin sync must be safe to run repeatedly.

Use:

```text
garmin_activity_id UNIQUE
```

Flow:

```text
fetch activity
    ↓
activity ID exists?
    ├── yes → update if needed
    └── no  → create
```

---

# 35. Dashboard

The dashboard should show:

## Today

```text
Today's workout
Why you're doing it
Target effort
```

## This week

```text
Planned runs
Completed runs
Weekly distance
Long run
Training load
```

## Progress

```text
Longest run
Average easy pace
HR trends
Cadence trends
Consistency
```

## 10K readiness

Do NOT present a fake precise percentage.

Instead show indicators:

```text
Continuous running: Improving
Long-run endurance: Developing
Weekly consistency: Strong
10K readiness: Developing
```

---

# 36. Progress scoring

Create separate scores rather than one magical score.

Example:

```text
Consistency score
Endurance score
Aerobic efficiency score
Workout completion score
Recovery score
```

Then Gemini can explain the scores.

Avoid:

```text
Your 10K readiness is 73.42%
```

unless you have a validated model behind it.

---

# 37. Trend analysis

Track:

```text
Distance over time
Pace at similar effort
HR at similar pace
Long-run duration
Cadence
Weekly frequency
Training load
Workout completion
RPE
```

The most useful question is often:

> "Is the athlete producing better performance at the same effort?"

---

# 38. Personal records

Track:

```text
1 km
2 km
3 km
5 km
longest run
fastest average pace
best controlled effort
```

Do not encourage constant PR attempts.

A training PR can be useful, but training consistency is more important for this goal.

---

# 39. AI memory

Do not send the entire history to Gemini every time.

Create a compact athlete state:

```json
{
  "goal": "10K",
  "weeks_remaining": 11,
  "current_phase": "AEROBIC_DEVELOPMENT",
  "recent_volume_km": 15.4,
  "four_week_average_km": 13.8,
  "longest_run_km": 6.1,
  "average_easy_pace": "7:38",
  "recent_easy_hr": 151,
  "consistency": 0.82,
  "current_limitations": [],
  "recent_trends": []
}
```

Then send:

```text
Athlete state
+
recent runs
+
current workout
```

This reduces cost and context size.

---

# 40. Context windows

For a single run, use:

```text
current run
+
last 5–10 runs
+
current week
+
athlete state
```

For weekly analysis:

```text
last 4 weeks
+
current plan
+
athlete state
```

For monthly/deep analysis:

```text
8–12 weeks
+
trend summaries
```

Do not send hundreds of raw activities unnecessarily.

---

# 41. Cost optimization

Use model tiers.

### Every run

Gemini Flash / Flash-Lite.

### Weekly

Gemini Flash.

### Monthly

Higher-end Gemini model.

### Simple extraction

Flash-Lite.

Also:

- Cache identical analysis inputs.
- Hash prompts + data.
- Do not reanalyze unchanged runs.
- Store AI results.
- Keep prompts concise.
- Send calculated metrics rather than raw GPS streams unless needed.

---

# 42. Raw GPS data

Do not send the entire GPS polyline to Gemini by default.

Python can derive:

```text
distance
elevation
pace
splits
terrain
stops
```

Send those.

Only send detailed route information when geographic/terrain analysis is actually useful.

---

# 43. Observability

Track AI requests:

```text
model
latency
input_tokens
output_tokens
estimated_cost
success
validation_failure
retry_count
prompt_version
```

Create a table:

```text
AIRequestLog
-------------------------
id
model
operation
input_tokens
output_tokens
latency_ms
estimated_cost
status
error
created_at
```

This makes cost visible.

---

# 44. Reliability

Gemini calls can fail.

Implement:

```text
timeout
retry
exponential backoff
rate-limit handling
JSON validation
fallback model
```

Example:

```text
Gemini Coach model
       ↓ failure
Gemini cheaper model
       ↓ failure
Use deterministic recommendation
```

Do not leave the athlete without a workout just because an AI request failed.

---

# 45. Fallback plan

Maintain a deterministic fallback planner.

Example:

```text
If AI unavailable:

Use current approved weekly plan.

If fatigue flag:
    downgrade intensity.

If missed workout:
    don't compress sessions.

If injury flag:
    no progression.
```

---

# 46. Security

Store API keys only in environment variables or a secrets manager.

Never:

```text
commit GEMINI_API_KEY
```

Use:

```env
GEMINI_API_KEY=...
```

For production:

```text
AWS Secrets Manager
or
Kubernetes Secrets
or
another secrets manager
```

---

# 47. Privacy

Training data can contain sensitive personal information.

Store only what you need.

Avoid sending:

- unnecessary identity information
- exact home coordinates
- unrelated health information

When sending data to Gemini, use an internal athlete ID instead of the person's name where possible.

---

# 48. Django project structure

A good structure:

```text
backend/
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   └── asgi.py
│
├── apps/
│   ├── athletes/
│   │   ├── models/
│   │   ├── serializers/
│   │   ├── services/
│   │   ├── views/
│   │   └── urls.py
│   │
│   ├── training/
│   │   ├── models/
│   │   ├── services/
│   │   ├── selectors/
│   │   ├── serializers/
│   │   ├── views/
│   │   └── urls.py
│   │
│   ├── activities/
│   │   ├── models/
│   │   ├── providers/
│   │   ├── services/
│   │   └── tasks.py
│   │
│   ├── metrics/
│   │   ├── services/
│   │   ├── calculators/
│   │   └── tasks.py
│   │
│   ├── coaching/
│   │   ├── prompts/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── validators/
│   │   └── tasks.py
│   │
│   └── analytics/
│       ├── services/
│       └── views/
│
├── common/
│   ├── exceptions/
│   ├── utils/
│   ├── constants/
│   └── models/
│
├── requirements/
├── tests/
└── manage.py
```

---

# 49. Service boundaries

Do not make Django views directly call Gemini.

Bad:

```python
def analyze_run(request):
    gemini.generate_content(...)
```

Better:

```text
View
 ↓
Service
 ↓
Context builder
 ↓
Gemini client
 ↓
Validator
 ↓
Repository
```

Example:

```python
analysis = run_coaching_service.analyze(activity_id)
```

---

# 50. Testing

Test the deterministic calculations heavily.

## Unit tests

Test:

```text
pace calculation
split calculation
HR drift
cadence variability
weekly volume
load calculation
workout classification
```

## AI contract tests

Provide fixed inputs and validate:

```text
JSON schema
required fields
allowed enums
safety constraints
```

Do not test exact prose.

Test structure and behavior.

---

# 51. AI evaluation dataset

Create 30–100 representative runs.

Include:

```text
easy run
hard run
bad pacing
excellent pacing
high HR
low HR
heat
hills
walk/run
missed workouts
rapid progression
fatigue
pain report
```

Run your prompts against them.

Evaluate:

```text
Did the AI identify the important issue?
Did it avoid unsafe progression?
Did it invent data?
Did it produce valid JSON?
Was the recommendation reasonable?
```

This is much more important than simply choosing the "smartest" model.

---

# 52. Example complete run flow

```text
1. Garmin sync starts.

2. New activity detected.

3. Store activity.

4. Calculate:
   - pace
   - splits
   - HR drift
   - cadence
   - load
   - consistency

5. Check safety flags.

6. Build athlete context.

7. Send compact context to Gemini Flash.

8. Gemini returns structured JSON.

9. Validate response.

10. Store AIAnalysis.

11. Show user:
    - summary
    - good things
    - issues
    - recovery
    - next workout

12. At week's end:
    - aggregate all runs
    - generate weekly review
    - generate next week's plan
    - validate plan
    - store approved plan.
```

---

# 53. Example weekly flow

```text
Sunday
   ↓
Collect week's activities
   ↓
Calculate weekly metrics
   ↓
Generate weekly summary
   ↓
Gemini weekly coach
   ↓
Safety validation
   ↓
Plan next week
   ↓
Store plan
   ↓
User reviews plan
```

Ideally the user can approve the plan rather than silently changing it.

---

# 54. User interaction

A useful coach UI could look like:

```text
TODAY'S RUN

4.2 km
7:31/km
154 bpm
162 spm

Coach:

You kept your pace reasonably consistent today.
Your second half was slightly slower while HR rose,
which suggests the effort became harder as the run progressed.

Don't increase pace yet.

Next:
30–35 min easy running.

Focus:
Keep the effort conversational.
```

---

# 55. Weekly coach UI

```text
WEEK 6 REVIEW

Status: On track

You completed:
4 / 4 runs

Distance:
17.2 km

Longest run:
6.1 km

Key improvement:
Your easy-run pace improved while average HR
remained similar.

Main concern:
Your last long run showed significant fatigue.

Next week's focus:
Build endurance without adding much intensity.

Planned:
Tue — 35 min easy
Thu — 4 × 3 min controlled
Sat — 30 min easy
Sun — 6.5 km long easy
```

---

# 56. What NOT to build initially

Do not start with:

- Mobile app
- Complex ML model
- Predictive injury model
- Race-time prediction
- Computer vision
- Automatic medical recommendations
- Huge vector database
- RAG over random running articles

First build:

```text
Garmin
+
metrics
+
Gemini
+
adaptive plan
```

That is enough.

---

# 57. Phase 1 — MVP

Build only:

```text
Garmin sync
Run database
Metric calculations
Gemini run analysis
17-week baseline plan
Weekly review
```

No frontend required initially.

You can test using Django API + Postman.

---

# 58. Phase 2

Add:

```text
Workout feedback
Adaptive weekly planning
Training trends
Dashboard
Cost tracking
Prompt versioning
```

---

# 59. Phase 3

Add:

```text
Recovery data
Weather
Sleep
HRV if available
Advanced trend analysis
Deep monthly reviews
```

Only add data that actually improves decisions.

---

# 60. Phase 4

Potential future features:

```text
Race-day strategy
Race pacing recommendation
Estimated finish range
Training readiness
Automatic workout calendar
Natural-language coach chat
"What if I miss tomorrow's run?"
"Why was today's HR high?"
"Can I run faster?"
```

---

# 61. Natural-language coach

Eventually expose:

```text
POST /api/coach/ask/
```

User can ask:

```text
Why was my heart rate so high today?
```

Context builder retrieves:

```text
today's run
recent runs
weather
current plan
training state
```

Then Gemini answers.

This is much better than sending the entire database to Gemini.

---

# 62. RAG is optional

You do NOT need RAG for the first version.

If later you want evidence-backed coaching, create a curated knowledge base from reliable sources.

Then:

```text
User question
    ↓
Retrieve relevant evidence
    ↓
Gemini
    ↓
Answer with evidence
```

Do not fill a vector database with random fitness blogs.

---

# 63. Model selection strategy

Make the model configurable per operation:

```python
MODEL_CONFIG = {
    "run_analysis": "fast",
    "weekly_review": "coach",
    "plan_generation": "coach",
    "monthly_review": "deep",
    "simple_summary": "lite"
}
```

Then map:

```text
lite  → Gemini Flash-Lite
fast  → Gemini Flash
coach → Gemini Flash
deep  → higher-end Gemini reasoning model
```

You can change this later without rewriting business logic.

---

# 64. Cost strategy

The system should log:

```text
tokens per run
tokens per week
cost per month
```

You can then compare:

```text
Gemini Flash-Lite
vs
Gemini Flash
vs
higher-end Gemini
```

Do not optimize cost prematurely.

For a personal running coach, the total API usage should generally be small compared with most production AI workloads.

---

# 65. Recommended development order

## Step 1

Create Django project.

## Step 2

Create PostgreSQL models.

## Step 3

Implement Garmin activity ingestion.

## Step 4

Store activities and splits.

## Step 5

Build metrics engine.

## Step 6

Write unit tests for metrics.

## Step 7

Create Gemini client abstraction.

## Step 8

Create structured Gemini schemas.

## Step 9

Implement run analysis.

## Step 10

Implement baseline 17-week plan.

## Step 11

Implement weekly review.

## Step 12

Implement adaptive planning.

## Step 13

Add Celery.

## Step 14

Add dashboard/API.

## Step 15

Add observability and cost tracking.

---

# 66. Suggested repository structure

```text
running-coach/
├── backend/
│   ├── config/
│   ├── apps/
│   ├── common/
│   ├── requirements/
│   └── manage.py
│
├── infrastructure/
│   ├── docker/
│   ├── postgres/
│   └── redis/
│
├── docs/
│   ├── architecture.md
│   ├── ai-prompts.md
│   ├── metrics.md
│   └── training-logic.md
│
├── tests/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# 67. Example environment variables

```env
DJANGO_SECRET_KEY=
DATABASE_URL=
REDIS_URL=

GEMINI_API_KEY=

GEMINI_FAST_MODEL=
GEMINI_COACH_MODEL=
GEMINI_DEEP_MODEL=

GARMIN_USERNAME=
GARMIN_PASSWORD=
```

Never commit `.env`.

Commit:

```text
.env.example
```

---

# 68. Final system philosophy

The most important architectural decision is:

```text
                    ┌───────────────┐
                    │    Garmin     │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │    Django     │
                    └───────┬───────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
        ┌───────────────┐       ┌───────────────┐
        │ Python Metrics│       │ Training DB   │
        └───────┬───────┘       └───────┬───────┘
                │                       │
                └───────────┬───────────┘
                            ▼
                    ┌───────────────┐
                    │ Gemini Coach  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Safety Rules  │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Training Plan │
                    └───────────────┘
```

Gemini should be the **coach**, not the calculator, database, or safety gate.

That separation makes the system:

- cheaper
- testable
- explainable
- more reliable
- easier to upgrade
- safer

---

# 69. First MVP target

The first useful version should answer these five questions after every run:

1. **How did I perform?**
2. **What changed compared with recent runs?**
3. **What did I do well?**
4. **What should I improve?**
5. **What should my next workout be?**

And every Sunday:

1. **Am I progressing toward 10K?**
2. **Am I training too much or too little?**
3. **What is my biggest current limitation?**
4. **What should I do next week?**
5. **Does the 17-week plan need adjustment?**

If the system reliably answers those questions from Garmin data, you already have a very useful personal AI running coach.

---

# 70. Recommended first implementation

Start with these Django apps:

```text
athletes
activities
training
metrics
coaching
```

Then implement this pipeline first:

```text
Garmin activity
      ↓
RunActivity
      ↓
RunMetrics
      ↓
Gemini run analysis
      ↓
AIAnalysis
      ↓
Next workout
```

Once that works reliably, add:

```text
weekly review
      ↓
adaptive weekly plan
```

That should be the core of the 17-week system.
