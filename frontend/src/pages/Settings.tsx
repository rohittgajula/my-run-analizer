import { useState } from 'react'
import { useAuth } from '../lib/AuthContext'
import { ApiError, type Athlete } from '../lib/auth'
import { DayPicker } from '../components/DayPicker'
import { Field } from '../components/Field'

/** Seconds per km <-> "m:ss", because nobody thinks in 645. */
const toPace = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

const fromPace = (text: string): number | null => {
  const match = /^(\d{1,2}):([0-5]\d)$/.exec(text.trim())
  return match ? Number(match[1]) * 60 + Number(match[2]) : null
}

export default function Settings() {
  const { athlete, updateAthlete } = useAuth()
  const [draft, setDraft] = useState<Athlete | null>(athlete)
  const [paceText, setPaceText] = useState({
    min: toPace(athlete?.easy_pace_min ?? 600),
    max: toPace(athlete?.easy_pace_max ?? 645),
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!draft) return null

  const set = <K extends keyof Athlete>(key: K, value: Athlete[K]) => {
    setDraft({ ...draft, [key]: value })
    setSaved(false)
  }

  const numeric = (raw: string) => (raw === '' ? null : Number(raw))

  const save = async () => {
    setBusy(true)
    setErrors({})

    const min = fromPace(paceText.min)
    const max = fromPace(paceText.max)
    if (min === null || max === null) {
      setErrors({ easy_pace_min: 'Use m:ss, for example 10:00.' })
      setBusy(false)
      return
    }

    try {
      await updateAthlete({
        display_name: draft.display_name,
        timezone: draft.timezone,
        weight_kg: draft.weight_kg,
        resting_hr: draft.resting_hr,
        max_hr: draft.max_hr,
        easy_pace_min: min,
        easy_pace_max: max,
        hr_easy_min: draft.hr_easy_min,
        hr_easy_max: draft.hr_easy_max,
        hr_ceiling: draft.hr_ceiling,
        run_cadence_threshold: draft.run_cadence_threshold,
        available_days: draft.available_days,
        long_run_day: draft.long_run_day,
      })
      setSaved(true)
    } catch (caught) {
      setErrors(caught instanceof ApiError ? caught.fieldErrors() : { detail: 'Could not save.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <header className="header">
        <h1>Settings</h1>
      </header>

      <section className="card">
        <h2>You</h2>
        <Field label="Name">
          <input value={draft.display_name} onChange={(e) => set('display_name', e.target.value)} />
        </Field>
        <Field
          label="Timezone"
          error={errors.timezone}
          hint="Every date in the app is worked out from this."
        >
          <input value={draft.timezone} onChange={(e) => set('timezone', e.target.value)} />
        </Field>
        <Field label="Weight (kg)" hint="Optional. Scales hydration and fuelling figures.">
          <input
            type="number"
            step="0.1"
            value={draft.weight_kg ?? ''}
            onChange={(e) => set('weight_kg', numeric(e.target.value))}
          />
        </Field>
      </section>

      <section className="card">
        <h2>Training days</h2>
        <DayPicker
          value={draft.available_days}
          onChange={(next) => set('available_days', next)}
          longRunDay={draft.long_run_day}
          onLongRunDayChange={(day) => set('long_run_day', day)}
        />
        {errors.available_days && <p className="bad">{errors.available_days}</p>}
        {errors.long_run_day && <p className="bad">{errors.long_run_day}</p>}
      </section>

      <section className="card">
        <h2>Easy pace band</h2>
        <p className="muted">
          A starting reference, not a target. What today prescribes comes from the plan.
        </p>
        <div className="row">
          <Field label="Fast edge" error={errors.easy_pace_min}>
            <input
              value={paceText.min}
              onChange={(e) => {
                setPaceText({ ...paceText, min: e.target.value })
                setSaved(false)
              }}
              placeholder="10:00"
            />
          </Field>
          <Field label="Slow edge" error={errors.easy_pace_max}>
            <input
              value={paceText.max}
              onChange={(e) => {
                setPaceText({ ...paceText, max: e.target.value })
                setSaved(false)
              }}
              placeholder="10:45"
            />
          </Field>
        </div>
      </section>

      <section className="card">
        <h2>Heart rate</h2>
        <div className="row">
          <Field label="Easy min">
            <input
              type="number"
              value={draft.hr_easy_min}
              onChange={(e) => set('hr_easy_min', Number(e.target.value))}
            />
          </Field>
          <Field label="Easy max">
            <input
              type="number"
              value={draft.hr_easy_max}
              onChange={(e) => set('hr_easy_max', Number(e.target.value))}
            />
          </Field>
          <Field label="Ceiling" error={errors.hr_ceiling}>
            <input
              type="number"
              value={draft.hr_ceiling}
              onChange={(e) => set('hr_ceiling', Number(e.target.value))}
            />
          </Field>
        </div>
        <Field
          label="Run cadence threshold (spm)"
          hint="At or above this counts as running rather than walking. This is what separates your real running distance from the total."
        >
          <input
            type="number"
            value={draft.run_cadence_threshold}
            onChange={(e) => set('run_cadence_threshold', Number(e.target.value))}
          />
        </Field>
      </section>

      {errors.detail && <p className="bad">{errors.detail}</p>}

      <div className="row row-end">
        {saved && <span className="ok-note">Saved</span>}
        <button className="button" onClick={save} disabled={busy}>
          {busy ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </main>
  )
}
