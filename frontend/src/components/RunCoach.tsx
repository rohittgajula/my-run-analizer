import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/auth'
import { Card } from './Stat'

type Analysis = {
  available: boolean
  detail?: string
  summary?: string
  what_went_well?: string[]
  observations?: string[]
  possible_explanations?: string[]
  concerns?: string[]
  recovery?: { level: string; reason: string }
  next_focus?: string
}

const RECOVERY_TONE: Record<string, string> = { LOW: 'ok', MODERATE: 'warn', HIGH: 'bad' }

function List({ title, items, tone }: { title: string; items: string[]; tone?: string }) {
  if (!items?.length) return null
  return (
    <div className="coach-block">
      <h3 className={tone ? `tone-${tone}` : undefined}>{title}</h3>
      <ul className="plain">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

export function RunCoach({ id }: { id: number }) {
  const { data, isPending, error } = useQuery({
    queryKey: ['run-analysis', id],
    queryFn: () => api<Analysis>(`/activities/${id}/analysis/`),
    retry: false,
    staleTime: Infinity,   // cached server-side on the input hash; nothing changes it
  })

  if (isPending) {
    return <Card title="What this run tells you"><p className="muted">Reading it…</p></Card>
  }
  if (error || !data?.available) {
    return (
      <Card title="What this run tells you">
        <p className="muted">{data?.detail ?? 'Interpretation is unavailable right now.'}</p>
      </Card>
    )
  }

  return (
    <Card title="What this run tells you">
      <p className="coach-headline">{data.summary}</p>

      <List title="What went well" items={data.what_went_well ?? []} tone="ok" />
      <List title="Worth noticing" items={data.observations ?? []} />
      {/* Explanations are kept visibly separate from observations: heat, terrain and
          a slipping strap all produce numbers that look like lost fitness. */}
      <List title="Other explanations" items={data.possible_explanations ?? []} />
      <List title="Concerns" items={data.concerns ?? []} tone="bad" />

      {data.recovery && (
        <div className="coach-block">
          <h3 className={`tone-${RECOVERY_TONE[data.recovery.level] ?? 'neutral'}`}>
            Recovery need: {data.recovery.level.toLowerCase()}
          </h3>
          <p>{data.recovery.reason}</p>
        </div>
      )}

      {data.next_focus && (
        <div className="coach-block">
          <h3>Next time</h3>
          <p>{data.next_focus}</p>
        </div>
      )}
    </Card>
  )
}
