'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function JobActions({ jobId, status }: { jobId: string; status: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function act(action: 'retry' | 'abandon') {
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/jobs/${jobId}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(payload?.error ?? 'failed')
      return
    }
    router.refresh()
  }

  return (
    <div className="flex items-center gap-2">
      {status === 'failed' ? (
        <button disabled={busy} onClick={() => act('retry')} className="underline disabled:opacity-50">
          재시도
        </button>
      ) : null}
      {status === 'queued' || status === 'processing' ? (
        <button disabled={busy} onClick={() => act('abandon')} className="underline disabled:opacity-50">
          포기
        </button>
      ) : null}
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
