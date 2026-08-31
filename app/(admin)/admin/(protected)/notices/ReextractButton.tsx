'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { describeAdminApiFailure } from '@/lib/admin/admin-api-messages'

/** 확인 문구가 이 버튼의 본체다. 누르면 Gemini 호출이 실제로 발생하고
 *  (backend/app/services/content_extraction_service.py 가 --force 시 같은 notice
 *  행의 extracted_content 를 덮어쓴다), 기존 추출 결과는 되돌릴 수 없다.
 *
 *  "몇 건이 다시 도는지"는 항상 1건이다 — 이 버튼은 한 번에 이 공지 하나만
 *  대상으로 하고, 일괄 재추출 버튼은 만들지 않았다(사업 C 의 "재추출 금지"는
 *  자동 일괄 재추출을 막는 것이지, 관리자가 한 건씩 고르는 이 흐름은 별개다).
 *
 *  "얼마나 걸리는지"는 배포 설정을 그대로 인용한다 — 감이 아니다:
 *  EXTRACTOR_NOTICE_TIMEOUT_SECONDS=600, MAX_GEMINI_CALLS_PER_NOTICE=8
 *  (docs/content-extractor-job.md:115). */
const CONFIRM_MESSAGE = [
  '이 공지 하나를 강제로 다시 추출합니다.',
  '',
  '기존 추출 결과(첨부 분석·요약)를 덮어쓰며 되돌릴 수 없습니다.',
  'Gemini 호출이 최대 8회까지 실제로 발생하고, 완료까지 최대 10분이 걸릴 수 있습니다.',
  '',
  '계속하시겠습니까?',
].join('\n')

export default function ReextractButton({ noticeId }: { noticeId: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [isError, setIsError] = useState(false)

  async function run() {
    if (!confirm(CONFIRM_MESSAGE)) return
    setBusy(true)
    setMessage(null)
    setIsError(false)
    const response = await fetch(`/api/admin/notices/${noticeId}/reextract`, { method: 'POST' })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setIsError(true)
      setMessage(describeAdminApiFailure(response.status, payload?.error))
      return
    }
    setIsError(false)
    setMessage(`실행됨 (operation …${String(payload.operation).slice(-12)})`)
    router.refresh()
  }

  return (
    <div className="flex flex-col gap-1">
      <button disabled={busy} onClick={run} className="text-left text-rose-300 underline disabled:opacity-50">
        {busy ? '실행 중…' : '강제 재추출'}
      </button>
      {message ? (
        <span className={`max-w-[260px] text-xs ${isError ? 'text-rose-400' : 'text-slate-400'}`}>{message}</span>
      ) : null}
    </div>
  )
}
