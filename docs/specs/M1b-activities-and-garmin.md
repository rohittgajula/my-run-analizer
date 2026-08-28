# M1b — activities and Garmin ingestion

**Prerequisite: [M1a](M1a-identity.md) is done** — `Athlete`, `OwnedByAthlete` and login
all exist. Garmin connect attaches a token to a logged-in athlete, so it cannot be built
first without scaffolding a fake user and throwing it away.

**Goal:** your 17 Aug run visible in Django admin with its per-second records, imported
by a sync that is safe to re-run.

Four models. Nothing else. `Race`, `TrainingWeek`, `Workout`, `RunMetrics`, `AIAnalysis`
and `JournalEntry` wait until the code that fills them exists.

`run-project`'s equivalents are good and most of this is a straight port. Three places
deviate, marked **DEVIATE** — those are the ones to read carefully.

---

## 1. `Athlete` — built in M1a

See [M1a](M1a-identity.md). Nothing to add here.

---

## 2. `apps/ingest/models.py`

### `RawFitFile` — copy verbatim

```python
file           FileField(upload_to=fit_upload_path)
original_name  CharField(255)
sha256         CharField(64, db_index=True)
size_bytes     PositiveIntegerField
status         pending | parsed | failed
error          TextField(blank)
uploaded_at / parsed_at

Meta: UniqueConstraint(["athlete", "sha256"], name="uniq_athlete_fit_hash")

@staticmethod
def hash_bytes(data: bytes) -> str: ...
```

**Raw bytes are kept permanently.** Two reasons, both real: Garmin has no personal API so
the unofficial sync can break and manual export becomes the fallback; and your
segmentation algorithm *will* change, at which point every past activity needs
reprocessing from source rather than from a lossy summary.

The `(athlete, sha256)` constraint is one of the two idempotency layers.

---

## 3. `apps/activities/models.py`

### `Activity`

```python
garmin_activity_id  BigIntegerField(null, blank, db_index=True)
source              garmin_sync | fit_upload
raw_file            FK("ingest.RawFitFile", SET_NULL, null, blank)

sport               CharField(40, default="running")
started_at          DateTimeField(db_index=True)
local_date          DateField(db_index=True)   # via athlete.local_today, NOT localdate()

total_distance_m    FloatField(default=0)
total_timer_s       FloatField(default=0)
total_elapsed_s     FloatField(default=0)

avg_hr / max_hr     PositiveSmallIntegerField(null, blank)
avg_cadence_spm     FloatField(null, blank)
total_ascent_m      FloatField(null, blank)
total_descent_m     FloatField(null, blank)
calories            PositiveIntegerField(null, blank)

segmentation_version  IntegerField(null, blank)   # see DEVIATE 2
created_at

Meta:
  ordering = ["-started_at"]
  UniqueConstraint(["athlete", "garmin_activity_id"],
                   condition=Q(garmin_activity_id__isnull=False),
                   name="uniq_athlete_garmin_activity")
```

The conditional unique constraint is the second idempotency layer, and the condition
matters: without it, two manual uploads both with `garmin_activity_id=NULL` would collide.

**`local_date` is denormalised on purpose.** Deriving it at query time means every
"which runs were this week" query has to know the athlete's timezone. Store it once, at
ingest, from `athlete.local_today`.

**Weather fields are deliberately absent.** `run-project` has `temp_c`, `humidity_pct` and
friends here. They matter — heat is the most under-attributed cause of a bad session — but
they belong with the code that fills them. Open-Meteo serves historical data, so
backfilling later is a migration plus one script, not a re-collection.

### > DEVIATE 2 — version the derivation, don't flag it

`run-project` has `metrics_current = BooleanField()`, flipped false when the algorithm
changes. That tells you *that* a row is stale, never *how* stale, and it relies on someone
remembering to flip every row.

Store the version instead:

```python
segmentation_version = models.IntegerField(null=True, blank=True)
```

`NULL` means never processed. Then "everything that predates v4" is a query
(`segmentation_version__lt=4`), reprocessing is idempotent, and you can tell which
algorithm produced any given number — which matters the first time two runs disagree and
you need to know whether the athlete changed or the code did.

### `ActivityRecord` — copy verbatim

```python
activity     FK(Activity, CASCADE, related_name="records")
offset_s     FloatField                    # seconds since start

distance_m / speed_mps / cadence_spm / heart_rate / altitude_m
latitude / longitude
power_w / vertical_oscillation_mm / ground_contact_ms
stride_length_m / vertical_ratio / respiration_rate / temperature_c

Meta:
  ordering = ["offset_s"]
  indexes = [Index(fields=["activity", "offset_s"])]
```

**Everything is nullable.** Running-dynamics fields are present with a compatible sensor
and absent otherwise, and `None` must stay distinguishable from a measured zero.

**This is the table that makes the project possible.** Garmin's activity summary has no
per-second series, so without it segmentation cannot run and the 2.5 km / 1.0 km gap stays
invisible. A 28-minute run is ~1,670 rows — write them with `bulk_create`.

`Segment` belongs to M2, alongside the algorithm that produces it. Not now.

---

## 4. Files to copy from `run-project`

From `~/Desktop/run-project/backend/apps/ingest/`:

| File | Change needed |
|---|---|
| `fit_parser.py` | none |
| `services.py` | check it writes `local_date` from `athlete.local_today` |
| `garmin.py` | none — but read the comments |
| `garmin_connect.py` | none |
| `garmin_wellness.py` | defer; it needs a `DailyMetrics` model you do not have yet |
| `weather.py` | defer, per above |

**Then grep for `GARMIN_TOKEN_ROOT` and change it to `GARMIN_TOKEN_DIR`.** That is the one
rename that will bite, and it fails at runtime rather than at import.

Read `garmin.py` as you paste rather than after. Its comments record real failures — the
CLI that logs in and writes no token, the two-layer idempotency, why downloads are the
ORIGINAL `.fit` and not the JSON summary.

Pin `garminconnect==0.3.10` (already in `requirements.txt`). 0.2.x reads
`oauth1_token.json`; 0.3.x writes a combined `garmin_tokens.json`. Mixing them fails
confusingly.

Connect fresh from this app rather than reusing `run-project`'s token.

---

## Done tests

| Check | Expect |
|---|---|
| `manage.py check` | clean |
| `makemigrations && migrate` | applies without editing a migration by hand |
| Connect Garmin from the app | token directory non-empty afterwards — **verify this, do not trust "connected"** |
| First sync | your 17 Aug run appears in admin with `local_date` correct for Kolkata |
| `Activity.records.count()` | in the thousands, not zero |
| **Second sync, immediately** | 0 imported, all skipped. **The most important test here.** |
| Delete the `Activity`, keep `RawFitFile`, re-sync | still skipped — the sha256 layer catches it independently of the Garmin id |
| A record with no HR | stores `None`, not `0` |

The last idempotency test is worth doing deliberately. Two independent layers means
neither can silently stop working without the other covering — and you want to know they
both work while you have one run, not after fifty.
