import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from './api'
import { CATEGORY_LABEL, Chip, Spinner } from './ui'

const pct = (v) => `${Math.round(v * 100)}%`

function Stat({ label, value, sub, tone }) {
  const color = tone === 'good' ? 'var(--good-text)' : tone === 'bad' ? 'var(--critical)' : 'var(--ink)'
  return (
    <div className="card p-4 flex flex-col gap-1 min-w-0">
      <span className="text-xs" style={{ color: 'var(--ink-2)' }}>{label}</span>
      <span className="text-2xl font-semibold" style={{ color }}>{value}</span>
      {sub && <span className="text-xs" style={{ color: 'var(--muted)' }}>{sub}</span>}
    </div>
  )
}

const SERIES = [
  { key: 'escalation_recall', name: 'Escalation recall', color: 'var(--series-1)' },
  { key: 'escalation_precision', name: 'Escalation precision', color: 'var(--series-2)' },
  { key: 'auto_reply_rate', name: 'Auto-reply rate', color: 'var(--series-3)' },
]

function SweepTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="card p-2 text-xs shadow-lg tabular">
      <div className="font-semibold mb-1">Threshold {label}</div>
      {SERIES.map((s) => (
        <div key={s.key} className="flex items-center gap-2">
          <span className="inline-block w-3 h-0.5" style={{ background: s.color }} />
          <span style={{ color: 'var(--ink-2)' }}>{s.name}</span>
          <span className="ml-auto pl-3">{pct(row[s.key])}</span>
        </div>
      ))}
      <div className="mt-1" style={{ color: 'var(--ink-2)' }}>
        Unsafe auto-replies: <b style={{ color: 'var(--ink)' }}>{row.unsafe_auto_replies}</b> · unnecessary escalations: <b style={{ color: 'var(--ink)' }}>{row.unnecessary_escalations}</b>
      </div>
    </div>
  )
}

function ConfusionMatrix({ labels, matrix }) {
  const max = Math.max(1, ...matrix.flat())
  return (
    <div className="overflow-x-auto">
      <table className="text-xs tabular border-separate" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th className="text-left font-medium pr-2" style={{ color: 'var(--muted)' }}>gold ↓ / predicted →</th>
            {labels.map((l) => (
              <th key={l} className="font-medium px-1 pb-1 text-center" style={{ color: 'var(--ink-2)', minWidth: 52 }}>
                {CATEGORY_LABEL[l]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={labels[i]}>
              <th className="text-left font-medium pr-2 whitespace-nowrap" style={{ color: 'var(--ink-2)' }}>
                {CATEGORY_LABEL[labels[i]]}
              </th>
              {row.map((v, j) => {
                const t = v / max
                return (
                  <td
                    key={j}
                    className="text-center rounded h-9"
                    title={`gold ${labels[i]}, predicted ${labels[j]}: ${v}`}
                    style={{
                      background: v === 0 ? 'var(--surface-2)' : `color-mix(in oklab, var(--series-1) ${20 + 80 * t}%, var(--surface))`,
                      color: t > 0.5 ? '#fff' : 'var(--ink)',
                      outline: i === j ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    {v}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function EvalDashboard() {
  const [rep, setRep] = useState(null)
  const [err, setErr] = useState(null)
  const [onlyMisses, setOnlyMisses] = useState(true)

  useEffect(() => { api.evalReport().then(setRep).catch((e) => setErr(e.message)) }, [])

  const rows = useMemo(() => {
    if (!rep) return []
    return rep.tickets
      .map((t) => ({
        ...t,
        decisionMiss: t.gold_decision !== t.pred_decision,
        categoryMiss: t.pred_categories[0] !== t.gold_categories[0],
      }))
      .filter((t) => !onlyMisses || t.decisionMiss || t.categoryMiss)
  }, [rep, onlyMisses])

  if (err) return <div className="card p-6 text-sm" style={{ color: 'var(--critical)' }}>Could not load eval report: {err}</div>
  if (!rep) return <div className="card p-10 flex justify-center"><Spinner /></div>

  const c = rep.classification
  const e = rep.escalation
  const perf = rep.performance
  const th = rep.config.auto_reply_threshold

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-semibold">Evaluation on {rep.n_tickets} labelled tickets</h2>
        <span className="text-xs" style={{ color: 'var(--ink-2)' }}>
          {rep.config.classifier} + {rep.config.drafter} · threshold {th} · generated {new Date(rep.generated_at).toLocaleString()}
          {rep.n_errors > 0 && ` · ${rep.n_errors} errors`}
        </span>
      </div>

      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <Stat label="Category accuracy (primary)" value={pct(c.primary_accuracy)} sub={`micro-F1 ${c.micro_f1} across all labels`} />
        <Stat label="Decision accuracy" value={pct(e.accuracy)} sub={`auto-reply rate ${pct(e.auto_reply_rate)}`} />
        <Stat
          label="Unsafe auto-replies"
          value={e.unsafe_auto_replies}
          tone={e.unsafe_auto_replies === 0 ? 'good' : 'bad'}
          sub={`escalation recall ${pct(e.escalation_recall)}`}
        />
        <Stat
          label="Citations verified"
          value={pct(rep.citations.validity_rate)}
          sub={`${rep.citations.citations_valid}/${rep.citations.citations_total} quotes found in KB`}
        />
        <Stat label="Unnecessary escalations" value={e.unnecessary_escalations} sub={`escalation precision ${pct(e.escalation_precision)}`} />
        <Stat label="Angry-student recall" value={pct(rep.sentiment.angry_recall)} sub={`sentiment accuracy ${pct(rep.sentiment.accuracy)}`} />
        <Stat label="Latency per ticket" value={`${(perf.latency_ms_p50 / 1000).toFixed(1)}s`} sub={`p50 · p95 ${(perf.latency_ms_p95 / 1000).toFixed(1)}s`} />
        <Stat
          label="Cost per 1,000 tickets"
          value={`$${perf.cost_per_1000_tickets_usd_paid_tier.toFixed(2)}`}
          sub={`paid-tier prices · $0 on free tier · ${perf.fallback_calls} fallback calls`}
        />
      </div>

      {rep.holdout && (
        <section className="card p-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <div>
            <h3 className="font-semibold">Held-out set · {rep.holdout.n_tickets} new tickets</h3>
            <p className="text-xs" style={{ color: 'var(--ink-2)' }}>
              Written after prompt tuning and never used to tune it, so it shows whether the numbers above generalise.
            </p>
          </div>
          <span>Category <b>{pct(rep.holdout.classification.primary_accuracy)}</b></span>
          <span>Decision <b>{pct(rep.holdout.escalation.accuracy)}</b></span>
          <span>Unsafe auto-replies <b style={{ color: rep.holdout.escalation.unsafe_auto_replies ? 'var(--critical)' : 'var(--good-text)' }}>
            {rep.holdout.escalation.unsafe_auto_replies}</b></span>
          <span>Unnecessary escalations <b>{rep.holdout.escalation.unnecessary_escalations}</b></span>
          <span>Citations <b>{pct(rep.holdout.citations.validity_rate)}</b></span>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="card p-4 min-w-0">
          <h3 className="font-semibold text-sm">Auto-reply confidence threshold</h3>
          <p className="text-xs mb-3" style={{ color: 'var(--ink-2)' }}>
            Tickets below the threshold go to a human. Raising it catches more risky tickets (recall) but
            sends more answerable ones to humans (lower auto-reply rate). Recomputed from stored outputs, no extra LLM calls.
          </p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rep.threshold_sweep} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="threshold" tick={{ fill: 'var(--muted)', fontSize: 11 }} stroke="var(--grid)" />
                <YAxis domain={[0, 1]} tickFormatter={pct} tick={{ fill: 'var(--muted)', fontSize: 11 }} stroke="var(--grid)" />
                <Tooltip content={<SweepTooltip />} cursor={{ stroke: 'var(--muted)', strokeDasharray: '3 3' }} />
                <Legend wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
                <ReferenceLine x={th} stroke="var(--ink-2)" strokeDasharray="4 4"
                  label={{ value: 'current', fill: 'var(--ink-2)', fontSize: 11, position: 'insideTopRight' }} />
                {SERIES.map((s) => (
                  <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color}
                    strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card p-4 min-w-0">
          <h3 className="font-semibold text-sm mb-3">Primary category confusion matrix</h3>
          <ConfusionMatrix labels={c.confusion_matrix.labels} matrix={c.confusion_matrix.matrix} />
          <table className="w-full text-xs tabular mt-4">
            <thead style={{ color: 'var(--muted)' }}>
              <tr className="text-left">
                <th className="font-medium py-1">Category</th>
                <th className="font-medium text-right">Precision</th>
                <th className="font-medium text-right">Recall</th>
                <th className="font-medium text-right">F1</th>
                <th className="font-medium text-right">n</th>
              </tr>
            </thead>
            <tbody>
              {c.per_class.map((p) => (
                <tr key={p.category} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1">{CATEGORY_LABEL[p.category]}</td>
                  <td className="text-right">{p.precision.toFixed(2)}</td>
                  <td className="text-right">{p.recall.toFixed(2)}</td>
                  <td className="text-right">{p.f1.toFixed(2)}</td>
                  <td className="text-right">{p.support}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="card p-4 min-w-0">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h3 className="font-semibold text-sm">Per-ticket results</h3>
          <label className="text-xs flex items-center gap-1.5 cursor-pointer" style={{ color: 'var(--ink-2)' }}>
            <input type="checkbox" checked={onlyMisses} onChange={(ev) => setOnlyMisses(ev.target.checked)} />
            Show only mismatches
          </label>
          <span className="text-xs ml-auto" style={{ color: 'var(--muted)' }}>{rows.length} rows</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead style={{ color: 'var(--muted)' }}>
              <tr className="text-left">
                <th className="font-medium py-1 pr-2">ID</th>
                <th className="font-medium pr-2">Ticket</th>
                <th className="font-medium pr-2">Gold → predicted category</th>
                <th className="font-medium pr-2">Gold → predicted decision</th>
                <th className="font-medium pr-2 text-right">Conf.</th>
                <th className="font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.id} className="border-t align-top" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-2 pr-2 font-medium">{t.id}</td>
                  <td className="py-2 pr-2 max-w-xs">
                    <span className="line-clamp-2" title={t.text}>{t.text}</span>
                    <span style={{ color: 'var(--muted)' }}>{t.language} · {t.notes}</span>
                  </td>
                  <td className="py-2 pr-2">
                    <span>{t.gold_categories.map((x) => CATEGORY_LABEL[x]).join(' + ')}</span>
                    <br />
                    <span style={{ color: t.categoryMiss ? 'var(--critical)' : 'var(--good-text)' }}>
                      {t.categoryMiss ? '✗ ' : '✓ '}{t.pred_categories.map((x) => CATEGORY_LABEL[x]).join(' + ') || '—'}
                    </span>
                  </td>
                  <td className="py-2 pr-2 whitespace-nowrap">
                    <span>{t.gold_decision.replace('_', ' ')}</span>
                    <br />
                    {t.decisionMiss ? (
                      <Chip fg="var(--critical)" bg="var(--critical-soft)">
                        ✗ {t.pred_decision.replace('_', ' ')}
                        {t.gold_decision === 'escalate' ? ' (unsafe)' : ''}
                      </Chip>
                    ) : (
                      <span style={{ color: 'var(--good-text)' }}>✓ {t.pred_decision.replace('_', ' ')}</span>
                    )}
                  </td>
                  <td className="py-2 pr-2 text-right tabular">{t.confidence != null ? t.confidence.toFixed(2) : '—'}</td>
                  <td className="py-2" style={{ color: 'var(--ink-2)' }}>{t.reasons.join('; ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
