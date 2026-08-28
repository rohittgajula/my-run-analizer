import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, api, json } from '../lib/auth'

type Entry = {
  id: number
  text: string
  reply: string
  applies_to_date: string
  pain_reported: boolean
  illness_reported: boolean
  rpe: number | null
  extraction_failed: boolean
  extracted: Record<string, unknown> | null
  created_at: string
}

const PROMPTS = [
  'Ran 3k this morning, legs felt heavy after 2k',
  'Slept badly and work is stressful this week',
  'How do I build up to running longer?',
  'Why was my heart rate so high yesterday?',
]

function Facts({ entry }: { entry: Entry }) {
  const chips: string[] = []
  if (entry.pain_reported) {
    const where = (entry.extracted?.pain_location as string) ?? 'pain'
    chips.push(`pain: ${where}`)
  }
  if (entry.illness_reported) chips.push('unwell')
  if (entry.rpe) chips.push(`RPE ${entry.rpe}`)
  const distance = entry.extracted?.distance_mentioned_km as number | undefined
  if (distance) chips.push(`${distance} km`)

  if (!chips.length) return null
  return (
    <div className="chips">
      {chips.map((chip) => (
        <span key={chip} className={`chip ${chip.startsWith('pain') || chip === 'unwell' ? 'chip-bad' : ''}`}>
          {chip}
        </span>
      ))}
    </div>
  )
}

export default function Chat() {
  const client = useQueryClient()
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const history = useQuery({
    queryKey: ['journal'],
    queryFn: () => api<Entry[]>('/journal/'),
  })

  const send = useMutation({
    mutationFn: (message: string) =>
      api<Entry>('/coach/chat/', { method: 'POST', ...json({ message }) }),
    onSuccess: () => {
      setDraft('')
      setError('')
      // Anything the athlete said can change today's session, the readiness note and
      // the coaching read, so all three are refetched rather than left stale.
      for (const key of [['journal'], ['plan-session'], ['coach-guidance'], ['plan-today']]) {
        client.invalidateQueries({ queryKey: key })
      }
    },
    onError: (caught) =>
      setError(
        caught instanceof ApiError && caught.status === 429
          ? 'You have reached your coaching limit for now. Try again later.'
          : caught instanceof ApiError
            ? caught.message
            : 'Could not reach the coach.',
      ),
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history.data?.length, send.isPending])

  function submit(event: FormEvent) {
    event.preventDefault()
    if (draft.trim()) send.mutate(draft.trim())
  }

  const empty = !history.data?.length

  return (
    <main className="page">
      <header className="header">
        <h1>
          Coach<span className="mark">.</span>
        </h1>
        <p className="muted">
          Tell it anything — how a run went, how you slept, what hurts, what you are
          worried about. What you say changes the plan.
        </p>
      </header>

      <div className="chat">
        {empty && (
          <div className="chat-empty">
            <p className="muted">Nothing yet. Try one of these:</p>
            <div className="prompts">
              {PROMPTS.map((prompt) => (
                <button key={prompt} className="prompt" onClick={() => setDraft(prompt)}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.data?.map((entry) => (
          <div key={entry.id} className="turn">
            <div className="bubble bubble-you">{entry.text}</div>
            <div className="bubble bubble-coach">
              {entry.extraction_failed && (
                <p className="bad">Saved, but could not be read just now.</p>
              )}
              {entry.reply.split('\n\n').map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
              <Facts entry={entry} />
            </div>
          </div>
        ))}

        {send.isPending && (
          <div className="turn">
            <div className="bubble bubble-you">{send.variables}</div>
            <div className="bubble bubble-coach muted">Reading that…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="bad">{error}</p>}

      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="How did it go?"
          rows={2}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) submit(event)
          }}
        />
        <button className="button" disabled={send.isPending || !draft.trim()}>
          Send
        </button>
      </form>
      <p className="muted composer-hint">
        Anything you report as pain or illness stops the plan progressing until it
        settles. That rule is applied by the app, not decided in the conversation.
      </p>
    </main>
  )
}
