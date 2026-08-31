'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

interface Preview {
  schoolName: string
  noticeCount: number
  translationCount: number
  eventCount: number
  cardCount: number
  watermarkBoards: number
  hasWatermark: boolean
  estimatedFloodIfIgnored: number
}

/** 이 버튼의 본체는 확인 다이얼로그다. scripts/recrawl_trigger.py:51 은 확인
 *  없이 DELETE 를 던지고, 항상 watermark 까지 지운다 — «밀린 게 우르르 온다»의
 *  원인이다. 이 화면은 (1) 실제 영향 건수를 먼저 보여주고 사람이 그 숫자를
 *  서버가 다시 대조한 뒤에만 실행하고, (2) 워터마크를 지키는 쪽을 기본값으로
 *  두고, 워터마크를 무시하는 옵션은 따로 떼어 학교 이름을 그대로 입력해야만
 *  풀리게 한다. */
export default function RecrawlButton({ schoolId }: { schoolId: string }) {
  const router = useRouter()
  const [preview, setPreview] = useState<Preview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ignoreWatermark, setIgnoreWatermark] = useState(false)
  const [confirmName, setConfirmName] = useState('')

  function reset() {
    setPreview(null)
    setIgnoreWatermark(false)
    setConfirmName('')
    setError(null)
  }

  async function loadPreview() {
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schools/${schoolId}/recrawl`)
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      setError(payload?.error ?? 'preview_failed')
      return
    }
    setPreview(payload.preview)
  }

  async function execute() {
    if (!preview) return
    setBusy(true)
    setError(null)
    const response = await fetch(`/api/admin/schools/${schoolId}/recrawl`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        confirmNoticeCount: preview.noticeCount,
        ignoreWatermark,
        ...(ignoreWatermark ? { confirmSchoolName: confirmName } : {}),
      }),
    })
    const payload = await response.json().catch(() => null)
    setBusy(false)
    if (!response.ok || !payload?.ok) {
      // 409(preview_stale)면 건수가 바뀐 것 — 새 숫자를 보여주고 다시 묻는다.
      if (payload?.preview) setPreview(payload.preview)
      setError(payload?.error ?? 'recrawl_failed')
      return
    }
    reset()
    router.refresh()
  }

  if (!preview) {
    return (
      <button disabled={busy} onClick={loadPreview} className="underline disabled:opacity-50">
        {busy ? '확인 중…' : '재크롤'}
        {error ? <span className="ml-2 text-xs text-rose-400">{error}</span> : null}
      </button>
    )
  }

  const nameMatches = confirmName.trim() === preview.schoolName
  const canExecute = !busy && (!ignoreWatermark || nameMatches)

  return (
    <div className="flex w-72 flex-col gap-2 rounded border border-rose-800 bg-rose-950/40 p-2">
      <p className="text-xs font-semibold text-rose-200">되돌릴 수 없습니다</p>
      <p className="text-xs">
        {preview.schoolName} — 공지 {preview.noticeCount}건 · 번역 {preview.translationCount}건 ·
        일정 {preview.eventCount}건 · 카드 {preview.cardCount}건이 영구 삭제되고, discover-board
        재크롤이 큐에 들어갑니다.
      </p>

      {!preview.hasWatermark && (
        <p className="rounded bg-rose-900/60 p-1.5 text-xs text-rose-100">
          이 학교는 지금도 워터마크가 없습니다 — 아래 옵션과 무관하게 다음 크롤이
          게시판 상위 글을 전부 새 글로 처리할 수 있습니다.
        </p>
      )}

      <label className="flex items-start gap-1.5 text-xs text-amber-200">
        <input
          type="checkbox"
          checked={ignoreWatermark}
          onChange={(event) => {
            setIgnoreWatermark(event.target.checked)
            setConfirmName('')
          }}
          className="mt-0.5"
        />
        <span>
          워터마크를 무시하고 전체 재수집(위험) — 기본값은 워터마크를 지키는 쪽입니다.
          켜면 최대 약 {preview.estimatedFloodIfIgnored}건(추정, 게시판 스캔 깊이 기준)이
          이미 있던 글이어도 새 글로 재판정되어 다시 번역·발송될 수 있습니다.
        </span>
      </label>

      {ignoreWatermark && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-rose-200">
            확인을 위해 학교 이름(&ldquo;{preview.schoolName}&rdquo;)을 그대로 입력하세요.
          </label>
          <input
            value={confirmName}
            onChange={(event) => setConfirmName(event.target.value)}
            className="rounded border border-rose-700 bg-black/30 px-1.5 py-1 text-xs"
            placeholder={preview.schoolName}
          />
        </div>
      )}

      <div className="flex gap-3">
        <button
          disabled={!canExecute}
          onClick={execute}
          className={`underline disabled:opacity-50 ${ignoreWatermark ? 'text-rose-300' : 'text-amber-200'}`}
        >
          {busy ? '실행 중…' : ignoreWatermark ? '워터마크 무시하고 삭제+재크롤' : '삭제하고 재크롤'}
        </button>
        <button disabled={busy} onClick={reset} className="underline disabled:opacity-50">
          취소
        </button>
      </div>
      {error ? <span className="text-xs text-rose-400">{error}</span> : null}
    </div>
  )
}
