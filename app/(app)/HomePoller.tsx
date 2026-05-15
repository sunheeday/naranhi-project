'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

interface Props {
  /**
   * 현재 홈 리스트에서 비종결 상태(pending / processing)인 공지가 있는지 여부.
   * true일 때만 5초 간격으로 `router.refresh()`를 수행한다.
   */
  hasPending: boolean
}

/**
 * 홈 리스트에 processing/pending 상태 공지가 있을 때만 5초 간격으로
 * 서버 컴포넌트 트리를 재요청하여 실시간 갱신과 유사한 효과를 낸다.
 * 모든 공지가 ready/error가 되면 부모 서버 컴포넌트가 `hasPending=false`로
 * 재렌더되므로 useEffect 의존성으로 폴링이 자연스럽게 멈춘다.
 */
export default function HomePoller({ hasPending }: Props) {
  const router = useRouter()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!hasPending) return
    timerRef.current = setInterval(() => {
      router.refresh()
    }, 5000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [hasPending, router])

  return null
}
