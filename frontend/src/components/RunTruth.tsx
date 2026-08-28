import type { ActivityMetrics } from '../lib/auth'
import { duration, km, metres, pace } from '../lib/format'

/**
 * The run/walk split, shown as the headline rather than the footnote.
 *
 * A watch reports one number for two different activities. Showing "2.65 km" first
 * and the split underneath would reproduce exactly the impression this project exists
 * to correct, so the running distance leads and the logged total is the aside.
 */
export function RunTruth({ metrics, total }: { metrics: ActivityMetrics; total: number }) {
  const ran = metrics.run_block_count > 0

  return (
    <div className="truth">
      <div className="truth-bar" aria-hidden="true">
        <span className="truth-run" style={{ width: `${metrics.run_fraction * 100}%` }} />
      </div>

      <div className="truth-headline">
        <strong className="truth-primary">{metres(metrics.run_distance_m)}</strong>
        <span className="muted"> run</span>
        <span className="truth-sep">·</span>
        <span>{metres(metrics.walk_distance_m)}</span>
        <span className="muted"> walked</span>
      </div>

      <p className="truth-aside">
        Logged as {km(total)} — {(metrics.run_fraction * 100).toFixed(0)}% of it running
      </p>

      {ran && (
        <dl className="stats">
          <div>
            <dt>Longest block</dt>
            <dd className="data">{duration(metrics.longest_run_s)}</dd>
          </div>
          <div>
            <dt>Blocks</dt>
            <dd>{metrics.run_block_count}</dd>
          </div>
          <div>
            <dt>Run pace</dt>
            <dd className="data">{pace(metrics.run_pace_s_per_km)}<span className="unit">/km</span></dd>
          </div>
          <div>
            <dt>Walk pace</dt>
            <dd>{pace(metrics.walk_pace_s_per_km)}<span className="unit">/km</span></dd>
          </div>
          {metrics.avg_run_hr && (
            <div>
              <dt>Run HR</dt>
              <dd>{metrics.avg_run_hr}<span className="unit">bpm</span></dd>
            </div>
          )}
          {metrics.avg_run_cadence_spm && (
            <div>
              <dt>Run cadence</dt>
              <dd>{Math.round(metrics.avg_run_cadence_spm)}<span className="unit">spm</span></dd>
            </div>
          )}
        </dl>
      )}

      {ran && metrics.blended_pace_s_per_km && metrics.run_pace_s_per_km && (
        <p className="truth-note">
          Your watch showed {pace(metrics.blended_pace_s_per_km)}/km — the average of
          running and walking, which describes neither.
        </p>
      )}
    </div>
  )
}
