'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  schoolId: string
  showFailure?: boolean
}

const RETRY_COOLDOWN_MS = 5 * 60 * 1000

export default function SchoolCrawlerKickoff({ schoolId, showFailure = true }: Props) {
  const router = useRouter()
  const startedRef = useRef(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true

    const key = `naranhi:crawl-kickoff:${schoolId}`
    const previousAttempt = Number(window.localStorage.getItem(key) ?? '0')
    if (Number.isFinite(previousAttempt) && Date.now() - previousAttempt < RETRY_COOLDOWN_MS) {
      return
    }
    window.localStorage.setItem(key, String(Date.now()))

    let cancelled = false

    async function run() {
      try {
        const response = await fetch(`/api/schools/${encodeURIComponent(schoolId)}/crawl`, {
          method: 'POST',
          cache: 'no-store',
        })
        if (!response.ok && !cancelled) {
          setFailed(true)
        }
      } catch {
        if (!cancelled) {
          setFailed(true)
        }
      } finally {
        if (!cancelled) {
          router.refresh()
        }
      }
    }

    void run()

    return () => {
      cancelled = true
    }
  }, [router, schoolId])

  if (!failed || !showFailure) return null

  return (
    <p className="mt-2 text-xs text-muted-soft text-center">
      공지 수집 요청이 실패했어요. 잠시 후 다시 시도됩니다.
    </p>
  )
}
