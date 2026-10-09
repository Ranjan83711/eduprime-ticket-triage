import { lazy, Suspense, useEffect, useState } from 'react'
import { api } from './api'
import Inbox from './Inbox'
import { Spinner } from './ui'

// Recharts is large; only load it when the Evaluation tab is opened.
const EvalDashboard = lazy(() => import('./EvalDashboard'))

const TABS = [
  { id: 'inbox', label: 'Inbox' },
  { id: 'eval', label: 'Evaluation' },
]

export default function App() {
  const [tab, setTab] = useState(() => (location.hash === '#eval' ? 'eval' : 'inbox'))
  const [health, setHealth] = useState(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'down' }))
  }, [])

  const choose = (id) => {
    setTab(id)
    history.replaceState(null, '', `#${id}`)
  }

  return (
    <div className="min-h-screen">
      <header className="border-b" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="mx-auto max-w-7xl px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div>
            <h1 className="text-lg font-semibold leading-tight">EduPrime Support Triage</h1>
            <p className="text-xs" style={{ color: 'var(--ink-2)' }}>
              Classifies student tickets, drafts cited replies, auto-replies or escalates
            </p>
          </div>
          <nav className="flex gap-1" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => choose(t.id)}
                className="px-3 py-1.5 rounded-lg text-sm font-medium cursor-pointer"
                style={tab === t.id
                  ? { background: 'var(--accent-soft)', color: 'var(--ink)' }
                  : { color: 'var(--ink-2)' }}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto text-xs flex items-center gap-2" style={{ color: 'var(--ink-2)' }}>
            {health?.models && (
              <span className="hidden md:inline">
                {health.models.classifier} · {health.models.drafter} · fallback {health.models.fallback}
              </span>
            )}
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: health?.status === 'ok' ? 'var(--good)' : 'var(--critical)' }}
            />
            {health?.status === 'ok' ? 'API online' : health ? 'API offline' : 'Connecting…'}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        {tab === 'inbox' ? <Inbox /> : (
          <Suspense fallback={<div className="card p-10 flex justify-center"><Spinner /></div>}>
            <EvalDashboard />
          </Suspense>
        )}
      </main>
    </div>
  )
}
