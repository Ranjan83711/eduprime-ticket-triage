async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* not JSON */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export const api = {
  health: () => request('/api/health'),
  tickets: () => request('/api/tickets'),
  triage: (text, channel) => request('/api/triage', { method: 'POST', body: JSON.stringify({ text, channel }) }),
  resolve: (id, reply) => request(`/api/tickets/${id}/resolve`, { method: 'POST', body: JSON.stringify({ reply }) }),
  evalReport: () => request('/api/eval'),
}
