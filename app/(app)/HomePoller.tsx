'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface Props {
  /**
   * 홈에서 공지 수집/처리가 아직 진행 중인지 여부.
   * true일 때만 5초 간격으로 `router.refresh()`를 수행한다.
   */
  active: boolean
  loadingLabel: string
}

/**
 * 홈에서 학교 crawl kick-off 직후 아직 notice row가 생기지 않았거나,
 * processing/pending 상태 notice가 남아 있을 때 5초 간격으로 refresh 한다.
 * 준비/처리 상태가 끝나면 부모 서버 컴포넌트가 `active=false`로 재렌더되므로
 * 폴링이 자연스럽게 멈춘다.
 */
export default function HomePoller({ active, loadingLabel }: Props) {
  const router = useRouter()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!active) return
    timerRef.current = setInterval(() => {
      router.refresh()
    }, 5000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [active, router])

  if (!active) return null

  return (
    <div className="fixed inset-0 z-50 pointer-events-none flex items-center justify-center">
      <div className="rounded-full bg-white/88 p-4 shadow-card backdrop-blur-[2px]">
        <LoadingSpinner size="lg" label={loadingLabel} />
      </div>
    </div>
  )
}
