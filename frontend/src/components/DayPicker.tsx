const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/**
 * Availability only — which days you *can* train, not what each is for. The plan
 * generator decides the workout type from the phase and last week's data.
 */
export function DayPicker({
  value, onChange, longRunDay, onLongRunDayChange,
}: {
  value: Record<string, boolean>
  onChange: (next: Record<string, boolean>) => void
  longRunDay: number
  onLongRunDayChange: (day: number) => void
}) {
  const selected = Object.entries(value).filter(([, on]) => on).length

  return (
    <div className="daypicker">
      <div className="daypicker-row">
        {DAYS.map((label, index) => {
          const key = String(index)
          const on = Boolean(value[key])
          return (
            <button
              key={key}
              type="button"
              className={`day ${on ? 'day-on' : ''}`}
              aria-pressed={on}
              onClick={() => {
                const next = { ...value, [key]: !on }
                onChange(next)
                // A long-run day you are not available for is rejected by the API.
                // Move it rather than letting the user discover that on submit.
                if (on && longRunDay === index) {
                  const fallback = Object.entries(next).find(([, v]) => v)?.[0]
                  if (fallback) onLongRunDayChange(Number(fallback))
                }
              }}
            >
              {label}
            </button>
          )
        })}
      </div>

      <p className="field-hint">
        {selected === 0
          ? 'Pick at least one day you can train.'
          : `${selected} day${selected === 1 ? '' : 's'} a week.`}
      </p>

      <div className="field">
        <span className="field-label">Long run day</span>
        <select
          value={longRunDay}
          onChange={(event) => onLongRunDayChange(Number(event.target.value))}
        >
          {DAYS.map((label, index) =>
            value[String(index)] ? (
              <option key={index} value={index}>
                {label}
              </option>
            ) : null,
          )}
        </select>
        <span className="field-hint">The one day with time for a longer session.</span>
      </div>
    </div>
  )
}
