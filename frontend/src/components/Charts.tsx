import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
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

function Box({ children }: { children: React.ReactElement }) {
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  )
}

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
        <Bar dataKey={dataKey} radius={[2, 2, 0, 0]}>
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
