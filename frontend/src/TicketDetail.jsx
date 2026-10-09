import { Fragment, useState } from 'react'
import { api } from './api'
import { CATEGORY_LABEL, Chip, SENTIMENT, StatusChip, TEAM_LABEL } from './ui'

function Section({ title, children, right }) {
  return (
    <section className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--muted)' }}>{title}</h3>
        <div className="ml-auto">{right}</div>
      </div>
      {children}
    </section>
  )
}

// Render the reply with [n] markers as clickable superscripts linked to the citation list.
function ReplyWithCitations({ reply, checks, active, onPick }) {
  const byMarker = Object.fromEntries(checks.map((c) => [c.marker, c]))
  const parts = reply.split(/(\[\d+\])/g)
  return (
    <p className="text-sm leading-relaxed whitespace-pre-wrap">
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/)
        if (!m) return <Fragment key={i}>{part}</Fragment>
        const n = Number(m[1])
        const ok = byMarker[n]?.valid
        return (
          <button
            key={i}
            onClick={() => onPick(n)}
            className="align-super text-[10px] font-bold px-1 mx-0.5 rounded cursor-pointer"
            style={{
              color: ok ? 'var(--accent)' : 'var(--critical)',
              background: active === n ? 'var(--accent-soft)' : 'transparent',
            }}
            title={ok ? 'Verified citation' : 'Citation failed verification'}
          >
            [{n}]
          </button>
        )
      })}
    </p>
  )
}

export default function TicketDetail({ ticket, onUpdated }) {
  const r = ticket.result
  const cls = r.classification
  const draft = r.draft
  const checks = r.citation_checks || []
  const passagesById = Object.fromEntries((r.passages || []).map((p) => [p.id, p]))
  const [active, setActive] = useState(null)
  const [reply, setReply] = useState(draft?.reply || '')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState(null)

  const escalated = r.decision.decision === 'escalate'
  const pending = ticket.status === 'pending_review'

  const send = async () => {
    setSending(true)
    setErr(null)
    try {
      onUpdated(await api.resolve(ticket.id, reply))
    } catch (e) {
      setErr(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Decision banner */}
      <div
        className="rounded-xl p-4 border flex flex-col gap-2"
        style={{
          background: escalated ? 'var(--critical-soft)' : 'var(--good-soft)',
          borderColor: 'var(--border)',
        }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold" style={{ color: escalated ? 'var(--critical)' : 'var(--good-text)' }}>
            {escalated ? `! Escalated to ${TEAM_LABEL[r.decision.team] || 'a human'}` : '✓ Safe to auto-reply'}
          </span>
          <StatusChip status={ticket.status} />
          <span className="ml-auto text-xs tabular" style={{ color: 'var(--ink-2)' }}>
            {(r.total_latency_ms / 1000).toFixed(1)}s · {r.llm_calls.length} LLM calls
          </span>
        </div>
        <ul className="text-sm list-disc pl-5" style={{ color: 'var(--ink-2)' }}>
          {r.decision.reasons.map((x) => <li key={x}>{x}</li>)}
        </ul>
      </div>

      <Section title={`Ticket #${ticket.id} · ${ticket.channel}`}>
        <p className="text-sm whitespace-pre-wrap">{ticket.text}</p>
        {(r.precheck.flags.length > 0 || r.precheck.order_ids.length > 0 || r.precheck.utr_numbers.length > 0) && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {r.precheck.flags.map((f) => (
              <Chip key={f} fg="var(--critical)" bg="var(--critical-soft)" title="Rule-based pre-check (no LLM)">
                ⚑ {f.replaceAll('_', ' ')}
              </Chip>
            ))}
            {r.precheck.order_ids.map((o) => <Chip key={o}>Order {o}</Chip>)}
            {r.precheck.utr_numbers.map((u) => <Chip key={u}>UTR {u}</Chip>)}
          </div>
        )}
      </Section>

      {cls && (
        <Section title="Classification">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-1.5">
                {cls.categories.map((c, i) => (
                  <Chip key={c} fg="var(--ink)" bg={i === 0 ? 'var(--accent-soft)' : 'var(--surface-2)'}>
                    {CATEGORY_LABEL[c] || c}
                  </Chip>
                ))}
                <Chip fg={SENTIMENT[cls.sentiment].fg} bg={SENTIMENT[cls.sentiment].bg}>
                  {SENTIMENT[cls.sentiment].label}
                </Chip>
                {cls.at_risk && <Chip fg="var(--critical)" bg="var(--critical-soft)">At risk</Chip>}
                <Chip>{cls.language}</Chip>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1" style={{ color: 'var(--ink-2)' }}>
                  <span>Confidence</span>
                  <span className="tabular">{Math.round(cls.confidence * 100)}%</span>
                </div>
                <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--surface-2)' }}>
                  <div className="h-full rounded-full" style={{ width: `${cls.confidence * 100}%`, background: 'var(--accent)' }} />
                </div>
              </div>
              <p className="text-xs" style={{ color: 'var(--ink-2)' }}>
                Needs staff action: <b>{cls.requires_human_action ? 'yes' : 'no'}</b>
              </p>
            </div>
            <div>
              <p className="text-xs mb-1" style={{ color: 'var(--muted)' }}>Issues found</p>
              <ul className="text-sm list-disc pl-5">
                {cls.issues.map((x) => <li key={x}>{x}</li>)}
              </ul>
            </div>
          </div>
        </Section>
      )}

      {draft && (
        <Section
          title={escalated ? 'Draft for the agent' : 'Reply sent'}
          right={checks.length > 0 && (
            <Chip
              fg={checks.every((c) => c.valid) ? 'var(--good-text)' : 'var(--critical)'}
              bg={checks.every((c) => c.valid) ? 'var(--good-soft)' : 'var(--critical-soft)'}
            >
              {checks.filter((c) => c.valid).length}/{checks.length} citations verified
            </Chip>
          )}
        >
          {pending ? (
            <div className="flex flex-col gap-2">
              <textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={7}
                className="w-full rounded-lg p-3 text-sm border"
                style={{ borderColor: 'var(--border)', background: 'var(--page)', color: 'var(--ink)' }}
                aria-label="Reply to send"
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={send}
                  disabled={sending || !reply.trim()}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 cursor-pointer"
                  style={{ background: 'var(--accent)' }}
                >
                  {sending ? 'Sending…' : 'Approve & send'}
                </button>
                <span className="text-xs" style={{ color: 'var(--muted)' }}>
                  Edit if needed. Simulated send: it is logged, not emailed.
                </span>
              </div>
              {err && <p className="text-sm" style={{ color: 'var(--critical)' }}>{err}</p>}
            </div>
          ) : (
            <ReplyWithCitations
              reply={ticket.final_reply || draft.reply}
              checks={checks}
              active={active}
              onPick={setActive}
            />
          )}

          {checks.length > 0 && (
            <ol className="mt-4 flex flex-col gap-2">
              {checks.map((c) => {
                const p = passagesById[c.passage_id]
                return (
                  <li
                    key={`${c.marker}-${c.passage_id}`}
                    className="rounded-lg p-3 text-xs border"
                    style={{
                      borderColor: active === c.marker ? 'var(--accent)' : 'var(--border)',
                      background: 'var(--page)',
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <b>[{c.marker}]</b>
                      <span style={{ color: 'var(--ink-2)' }}>{p?.title || c.passage_id || '—'}</span>
                      <span className="ml-auto font-semibold" style={{ color: c.valid ? 'var(--good-text)' : 'var(--critical)' }}>
                        {c.valid ? '✓ verified in KB' : `✗ ${c.reason}`}
                      </span>
                    </div>
                    {c.quote && <q className="italic" style={{ color: 'var(--ink-2)' }}>{c.quote}</q>}
                  </li>
                )
              })}
            </ol>
          )}
        </Section>
      )}

      <Section title="Pipeline trace">
        <div className="overflow-x-auto">
          <table className="w-full text-xs tabular">
            <thead style={{ color: 'var(--muted)' }}>
              <tr className="text-left">
                <th className="py-1 pr-3 font-medium">Step</th>
                <th className="py-1 pr-3 font-medium">Model</th>
                <th className="py-1 pr-3 font-medium text-right">Tokens in/out</th>
                <th className="py-1 pr-3 font-medium text-right">Latency</th>
                <th className="py-1 font-medium text-right">Cost (paid tier)</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t" style={{ borderColor: 'var(--border)' }}>
                <td className="py-1.5 pr-3">pre-checks</td>
                <td className="py-1.5 pr-3" style={{ color: 'var(--ink-2)' }}>regex rules, no LLM</td>
                <td className="py-1.5 pr-3 text-right">—</td>
                <td className="py-1.5 pr-3 text-right">&lt;1 ms</td>
                <td className="py-1.5 text-right">$0</td>
              </tr>
              {r.llm_calls.map((c) => (
                <tr key={c.step} className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5 pr-3">{c.step}</td>
                  <td className="py-1.5 pr-3">
                    {c.model}
                    {c.fallback_used && <span className="ml-1" style={{ color: 'var(--critical)' }}>(fallback)</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right">{c.input_tokens}/{c.output_tokens}</td>
                  <td className="py-1.5 pr-3 text-right">{(c.latency_ms / 1000).toFixed(1)}s</td>
                  <td className="py-1.5 text-right">${c.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
              {r.passages.length > 0 && (
                <tr className="border-t" style={{ borderColor: 'var(--border)' }}>
                  <td className="py-1.5 pr-3 align-top">retrieve</td>
                  <td className="py-1.5" colSpan={4} style={{ color: 'var(--ink-2)' }}>
                    BM25 → {r.passages.map((p) => p.id).join(', ')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {r.error && <p className="text-xs mt-2" style={{ color: 'var(--critical)' }}>Error: {r.error}</p>}
      </Section>
    </div>
  )
}
