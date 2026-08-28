import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/auth'
import { Card } from './Stat'

export type Observation = {
  topic: string
  finding: string
  meaning: string
  action: string | null
}

type GuidanceResponse = {
  available: boolean
  cached?: boolean
  detail?: string
  budget?: boolean
  headline?: string
  doing_well?: Observation[]
  to_improve?: Observation[]
  stamina?: string
  cautions?: string[]
}

function Observations({ items, kind }: { items: Observation[]; kind: 'well' | 'improve' }) {
  return (
    <ul className="obs">
      {items.map((item) => (
        <li key={item.topic} className={`obs-${kind}`}>
          <div className="obs-topic">{item.topic}</div>
          <p className="obs-finding">{item.finding}</p>
          <p className="obs-meaning">{item.action ?? item.meaning}</p>
        </li>
      ))}
    </ul>
  )
}

/**
 * The coaching read.
 *
 * Degrades to an explanation rather than an error: the plan and its safety rules are
 * deterministic and do not need the model, so an outage costs interpretation, never
 * the training itself.
 */
export function Coach() {
  const { data, isPending, error } = useQuery({
    queryKey: ['coach-guidance'],
    queryFn: () => api<GuidanceResponse>('/coach/guidance/'),
    retry: false,
    // Cached server-side on the input hash, so re-asking the same question is free.
    staleTime: 1000 * 60 * 30,
  })

  if (isPending) {
    return (
      <Card title="Your coach" description="Reading your last four weeks…">
        <p className="muted">This takes a few seconds.</p>
      </Card>
    )
  }

  if (error || !data?.available) {
    return (
      <Card title="Your coach" description="Interpretation is unavailable right now.">
        <p className="muted">
          {data?.detail ?? 'Could not reach the coaching service.'}
        </p>
        <p className="muted">
          Your plan and its safety rules are worked out without the model, so nothing
          about your training depends on this.
        </p>
      </Card>
    )
  }

  return (
    <>
      <Card title="Your coach" description={data.cached ? 'From your last read — unchanged since.' : undefined}>
        <p className="coach-headline">{data.headline}</p>

        {data.stamina && (
          <div className="coach-block">
            <h3>Building stamina</h3>
            <p>{data.stamina}</p>
          </div>
        )}

        {!!data.cautions?.length && (
          <div className="notice notice-caution">
            <strong>Worth watching</strong>
            <ul>
              {data.cautions.map((caution) => (
                <li key={caution}>{caution}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <div className="grid grid-2">
        {!!data.doing_well?.length && (
          <Card title="What you're doing well" description="Each of these traces to a number in your own data.">
            <Observations items={data.doing_well} kind="well" />
          </Card>
        )}
        {!!data.to_improve?.length && (
          <Card title="What would help most" description="Ordered by what would change your outcome, not by how easy it is.">
            <Observations items={data.to_improve} kind="improve" />
          </Card>
        )}
      </div>
    </>
  )
}
