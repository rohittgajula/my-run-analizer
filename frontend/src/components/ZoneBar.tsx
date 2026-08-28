export type ZoneTotals = Record<string, number>

const ORDER = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5'] as const
const LABEL: Record<string, string> = {
  Z1: 'Recovery', Z2: 'Aerobic base', Z3: 'Steady', Z4: 'Threshold', Z5: 'Maximum',
}
// Z2 is the only zone shown in the data colour. Everything else is greyscale, so a
// glance at the bar answers the question that matters for building an aerobic base:
// how much of this was actually easy?
const FILL: Record<string, string> = {
  Z1: 'var(--ui-dim)',
  Z2: 'var(--data)',
  Z3: '#4a4a55',
  Z4: 'var(--warn)',
  Z5: 'var(--bad)',
}

const mins = (seconds: number) => `${Math.round(seconds / 60)}m`

export function ZoneBar({ totals }: { totals: ZoneTotals }) {
  const inZones = ORDER.map((z) => ({ zone: z, seconds: totals[z] ?? 0 }))
  const total = inZones.reduce((sum, z) => sum + z.seconds, 0)
  if (!total) return <p className="muted">No heart-rate data for this session.</p>

  const easy = ((totals.Z1 ?? 0) + (totals.Z2 ?? 0)) / total

  return (
    <>
      <div className="zonebar" role="img" aria-label="time spent in each heart-rate zone">
        {inZones
          .filter((z) => z.seconds > 0)
          .map((z) => (
            <span
              key={z.zone}
              style={{ width: `${(z.seconds / total) * 100}%`, background: FILL[z.zone] }}
              title={`${z.zone} ${LABEL[z.zone]} — ${mins(z.seconds)}`}
            />
          ))}
      </div>

      <dl className="zonelist">
        {inZones
          .filter((z) => z.seconds >= 20)
          .map((z) => (
            <div key={z.zone}>
              <dt>
                <span className="zonedot" style={{ background: FILL[z.zone] }} />
                {z.zone} {LABEL[z.zone]}
              </dt>
              <dd>
                {mins(z.seconds)}
                <span className="unit">{Math.round((z.seconds / total) * 100)}%</span>
              </dd>
            </div>
          ))}
      </dl>

      <p className="truth-note">
        {(easy * 100).toFixed(0)}% of this was easy (Z1–Z2).{' '}
        {easy < 0.7
          ? 'Aerobic base is built below Z3. Running easy days slightly too hard is the commonest reason it stalls.'
          : 'That is the balance that builds an aerobic base.'}
      </p>
    </>
  )
}
