import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

/**
 * Chart primitives sharing one set of axis, grid and tooltip conventions, so every
 * chart in the app reads the same way.
 *
 * Colour follows the same rule as the rest of the UI: `--data` cyan for a measured
 * series, and `--ok` / `--warn` / `--bad` only where a value carries a judgement.
 * Nothing is coloured to be decorative.
 */

const AXIS = { stroke: '#3a3a44', fontSize: 11, tickLine: false, axisLine: false }
const GRID = { stroke: '#1c1c22', strokeDasharray: '2 4' }

const shortDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

function Box({ children, tall }: { children: React.ReactElement; tall?: boolean }) {
  return (
    <div className={tall ? 'chart chart-tall' : 'chart'}>
      {/* debounce={0} because the default waits for a resize event that never comes
          in a backgrounded tab: the container measures zero on first paint and then
          nothing re-triggers it, leaving an empty div where a chart should be. */}
      <ResponsiveContainer width="100%" height="100%" debounce={0}>
        {children}
      </ResponsiveContainer>
    </div>
  )
}

// Charts render their final state immediately rather than animating in.
//
// Three reasons, in order of importance: a reader should not have to wait to read a
// number; an animation driven by requestAnimationFrame never completes in a
// backgrounded tab, so the chart sits blank; and every screenshot taken mid-animation
// shows a line that stops halfway, which looks exactly like missing data.
const NO_ANIMATION = { isAnimationActive: false } as const

const tooltip = {
  contentStyle: {
    background: '#0a0a0c',
    border: '1px solid #2b2b34',
    borderRadius: '0.5rem',
    fontSize: '0.82rem',
  },
  labelStyle: { color: '#6e6e7a' },
  cursor: { stroke: '#2b2b34' },
}

export function TrendLine({
  data, dataKey, domain, reference, referenceLabel,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  domain?: [number | 'auto', number | 'auto']
  reference?: number
  referenceLabel?: string
}) {
  return (
    <Box>
      <LineChart data={data} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDay} {...AXIS} minTickGap={24} />
        <YAxis domain={domain ?? ['auto', 'auto']} {...AXIS} width={38} />
        <Tooltip {...tooltip} labelFormatter={(v) => shortDay(String(v))} />
        {reference !== undefined && (
          <ReferenceLine
            y={reference}
            stroke="#5a5a66"
            strokeDasharray="3 3"
            label={{ value: referenceLabel, fill: '#6e6e7a', fontSize: 10, position: 'insideTopRight' }}
          />
        )}
        <Line
          type="monotone"
          dataKey={dataKey}
          stroke="#38e1ff"
          strokeWidth={2}
          dot={false}
          connectNulls
          {...NO_ANIMATION}
        />
      </LineChart>
    </Box>
  )
}

export function TrendArea({
  data, dataKey, domain,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  domain?: [number | 'auto', number | 'auto']
}) {
  return (
    <Box>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
        <defs>
          <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38e1ff" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#38e1ff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDay} {...AXIS} minTickGap={24} />
        <YAxis domain={domain ?? ['auto', 'auto']} {...AXIS} width={38} />
        <Tooltip {...tooltip} labelFormatter={(v) => shortDay(String(v))} />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke="#38e1ff"
          strokeWidth={2}
          fill="url(#fade)"
          connectNulls
          {...NO_ANIMATION}
        />
      </AreaChart>
    </Box>
  )
}

/** Bars coloured by a judgement the caller supplies — never by value for its own sake. */
export function JudgedBars({
  data, dataKey, colour, domain,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  colour: (row: Record<string, unknown>) => string
  domain?: [number | 'auto', number | 'auto']
}) {
  return (
    <Box>
      <BarChart data={data} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid {...GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDay} {...AXIS} minTickGap={24} />
        <YAxis domain={domain ?? ['auto', 'auto']} {...AXIS} width={38} />
        <Tooltip {...tooltip} labelFormatter={(v) => shortDay(String(v))} cursor={{ fill: '#12121a' }} />
        <Bar dataKey={dataKey} radius={[2, 2, 0, 0]} {...NO_ANIMATION}>
          {data.map((row, index) => (
            <Cell key={index} fill={colour(row)} />
          ))}
        </Bar>
      </BarChart>
    </Box>
  )
}

/** A ring gauge, in the spirit of Garmin's — but only where a 0-100 score exists. */
export function Ring({
  value, max = 100, label, tone = '#38e1ff',
}: {
  value: number | null
  max?: number
  label?: string
  tone?: string
}) {
  const size = 92
  const stroke = 9
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const fraction = value == null ? 0 : Math.max(0, Math.min(value / max, 1))

  return (
    <div className="ring">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
           aria-label={`${label ?? 'score'} ${value ?? 'unknown'} of ${max}`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1c1c22" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke={tone} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={`${circumference * fraction} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-value">{value ?? '—'}</div>
    </div>
  )
}


/**
 * The run itself, over time.
 *
 * Run blocks are shaded behind the trace so heart rate and cadence can be read
 * against what the athlete was actually doing — a heart rate of 160 means one thing
 * mid-run block and another thing while walking, and a chart that hides the
 * difference invites the wrong reading.
 */
export function RunTrace({
  points, series, blocks, invert, unit,
}: {
  points: Array<Record<string, number | null>>
  series: 'hr' | 'cadence' | 'pace' | 'altitude'
  blocks?: Array<{ kind: string; start_offset_s: number; duration_s: number }>
  invert?: boolean
  unit?: string
}) {
  const colour = { hr: '#ff4d6d', cadence: '#3ddc97', pace: '#38e1ff', altitude: '#8a8a99' }[series]
  const runBlocks = (blocks ?? []).filter((b) => b.kind === 'run')

  const label = (value: number) =>
    series === 'pace'
      ? `${Math.floor(value / 60)}:${String(Math.round(value) % 60).padStart(2, '0')}`
      : String(Math.round(value))

  return (
    <div className="chart chart-tall">
      <ResponsiveContainer width="100%" height="100%" debounce={0}>
        <LineChart data={points} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid {...GRID} vertical={false} />
          {runBlocks.map((block, index) => (
            <ReferenceArea
              key={index}
              x1={block.start_offset_s}
              x2={block.start_offset_s + block.duration_s}
              fill="#38e1ff"
              fillOpacity={0.07}
              strokeOpacity={0}
            />
          ))}
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(v) => `${Math.round(Number(v) / 60)}m`}
            {...AXIS}
            minTickGap={30}
          />
          <YAxis
            domain={['auto', 'auto']}
            reversed={invert}
            tickFormatter={(v) => label(Number(v))}
            {...AXIS}
            width={42}
          />
          <Tooltip
            {...tooltip}
            labelFormatter={(v) => `${Math.floor(Number(v) / 60)}:${String(Number(v) % 60).padStart(2, '0')}`}
            formatter={(v) => [`${label(Number(v))}${unit ? ` ${unit}` : ''}`, series]}
          />
          <Line type="monotone" dataKey={series} stroke={colour} strokeWidth={1.6} dot={false} connectNulls {...NO_ANIMATION} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
