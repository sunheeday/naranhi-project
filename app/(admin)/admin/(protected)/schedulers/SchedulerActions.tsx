'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { describeAdminApiFailure } from '@/lib/admin/admin-api-messages'

/** 확인 창에 "무엇이 멈추는지"를 구체적으로 적기 위한 문구.
 *  backend/app/services/gcp_admin_service.py:CONTROLLABLE_SCHEDULERS 가 정본이고
 *  (2026-08-29 gcloud 읽기 전용 확인으로 -1900/-2000 로 바로잡힌 이름이다),
 *  이 맵은 그 네 이름에 대한 화면 문구일 뿐 — 화이트리스트는 여기가 아니라
 *  백엔드 상수가 막는다(이름이 이 맵에 없어도 controllable=false 면 버튼 자체가 없다). */
const CONSEQUENCE_BY_NAME: Record<string, string> = {
  'naranhi-school-crawler-0600': '06시 학교 공지 크롤이 멈춥니다.',
  'naranhi-school-crawler-1900': '19시 학교 공지 크롤이 멈춥니다.',
  'naranhi-content-extractor-0700': '07시 공지 본문 추출이 멈춥니다.',
  'naranhi-content-extractor-2000': '20시 공지 본문 추출이 멈춥니다.',
}

export default function SchedulerActions({
  name,
  state,
  controllable,
}: {
  name: string
  state: string | null
  controllable: boolean
}) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!controllable) {
    return <span className="text-xs text-slate-500">화이트리스트 밖</span>
  }

  const action = state === 'PAUSED' ? 'resume' : 'pause'
  const label = action === 'resume' ? '재개' : '정지'

  async function run() {
    // 정지는 실수로 누르면 학부모에게 새 공지가 조용히 안 가는 방향으로만 어긋난다.
    // 재개는 상대적으로 안전하다(늦게 켜져도 다음 주기에 다시 돈다) — 확인 창은
    // 정지에만 둔다.
    if (action === 'pause') {
      const consequence = CONSEQUENCE_BY_NAME[name] ?? `${name} 실행이 멈춥니다.`
      const confirmed = confirm(
        `${name} 을(를) 지금 정지합니다.\n\n${consequence}\n정지 중에는 새 공지가 학부모에게 가지 않습니다. 재개 전까지 계속 멈춰 있습니다.\n\n계속하시겠습니까?`,
      )
      if (!confirmed) return
    }

    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schedulers/${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(describeAdminApiFailure(response.status, payload?.error))
      return
    }
    router.refresh()
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <button
          disabled={busy}
          onClick={run}
          className={`underline disabled:opacity-50 ${action === 'pause' ? 'text-rose-300' : 'text-emerald-300'}`}
        >
          {busy ? '처리 중…' : label}
        </button>
      </div>
      {error ? <span className="max-w-[320px] text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
