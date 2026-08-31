'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

export default function AdminLoginForm() {
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const response = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      // 계정 존재 여부·잠금 여부를 문구로 구별하지 않는다.
      setError('아이디 또는 비밀번호가 올바르지 않습니다.')
      return
    }
    router.replace(payload.next ?? '/admin')
    router.refresh()
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full max-w-sm flex-col gap-3">
      <input
        className="rounded border border-slate-700 bg-slate-900 px-3 py-2"
        autoComplete="username"
        placeholder="아이디"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <input
        className="rounded border border-slate-700 bg-slate-900 px-3 py-2"
        type="password"
        autoComplete="current-password"
        placeholder="비밀번호"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-100 px-3 py-2 font-medium text-slate-900 disabled:opacity-50"
      >
        {busy ? '확인 중…' : '로그인'}
      </button>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
    </form>
  )
}
