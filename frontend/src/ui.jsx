// Small shared UI pieces and labels.

export const CATEGORY_LABEL = {
  refund: 'Refund',
  payment: 'Payment',
  batch_access: 'Batch access',
  technical: 'Technical',
  academic_doubt: 'Academic doubt',
  other: 'Other',
}

export const TEAM_LABEL = {
  billing: 'Billing',
  academic_ops: 'Academic Ops',
  tech_support: 'Tech Support',
  mentors: 'Subject Mentors',
  senior_support: 'Senior Support',
  support: 'Support',
}

export const STATUS = {
  auto_sent: { label: 'Auto-replied', icon: '✓', fg: 'var(--good-text)', bg: 'var(--good-soft)' },
  pending_review: { label: 'Needs human', icon: '!', fg: 'var(--critical)', bg: 'var(--critical-soft)' },
  sent_by_agent: { label: 'Sent by agent', icon: '✓', fg: 'var(--ink-2)', bg: 'var(--surface-2)' },
  send_failed: { label: 'Send failed', icon: '✗', fg: 'var(--critical)', bg: 'var(--critical-soft)' },
}

// Statuses where a person has to act.
export const NEEDS_HUMAN = new Set(['pending_review', 'send_failed'])

export const SENTIMENT = {
  calm: { label: 'Calm', fg: 'var(--ink-2)', bg: 'var(--surface-2)' },
  frustrated: { label: 'Frustrated', fg: 'var(--ink)', bg: 'var(--warn-soft)' },
  angry: { label: 'Angry', fg: 'var(--critical)', bg: 'var(--critical-soft)' },
}

export function Chip({ children, fg = 'var(--ink-2)', bg = 'var(--surface-2)', title }) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap"
      style={{ color: fg, background: bg }}
    >
      {children}
    </span>
  )
}

export function StatusChip({ status }) {
  const s = STATUS[status] || STATUS.pending_review
  return (
    <Chip fg={s.fg} bg={s.bg}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </Chip>
  )
}

export function Spinner() {
  return (
    <span
      className="inline-block w-4 h-4 border-2 rounded-full animate-spin"
      style={{ borderColor: 'var(--grid)', borderTopColor: 'var(--accent)' }}
      aria-label="Loading"
    />
  )
}

export function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
