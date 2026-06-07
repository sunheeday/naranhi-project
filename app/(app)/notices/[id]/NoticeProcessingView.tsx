'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import CharacterImage from '@/components/brand/CharacterImage'

interface Props {
  title: string
  description: string
  progressLabel: string
}

export default function NoticeProcessingView({ title, description, progressLabel }: Props) {
  const router = useRouter()

  // 5초마다 페이지 refresh로 상태 재확인
  useEffect(() => {
    const t = setInterval(() => {
      router.refresh()
    }, 5000)
    return () => clearInterval(t)
  }, [router])

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 gap-6">
      <div className="flex flex-col items-center gap-4">
        <CharacterImage character="standingPaper" size={120} disc />
        <h1 className="text-lg font-bold text-text-primary text-center">{title}</h1>
        <p className="text-sm text-text-secondary text-center">{description}</p>
        <div className="w-full max-w-sm rounded-full bg-border/80 p-1 shadow-soft" aria-label={progressLabel}>
          <div className="h-3 w-[62%] rounded-full bg-[linear-gradient(90deg,#1FB6FF_0%,#2F80ED_100%)] animate-pulse" />
        </div>
        <p className="text-sm font-semibold text-primary">{progressLabel}</p>
      </div>

      {/* 카드 스켈레톤 */}
      <div className="w-full max-w-app px-2 flex flex-col gap-3 mt-4">
        <div className="bg-surface rounded-card shadow-card p-5 animate-pulse">
          <div className="h-6 w-20 bg-border rounded-pill mb-4" />
          <div className="h-4 w-3/4 bg-border rounded mb-2" />
          <div className="h-4 w-1/2 bg-border rounded" />
        </div>
        <div className="bg-surface rounded-card shadow-card p-5 animate-pulse">
          <div className="h-6 w-24 bg-border rounded-pill mb-4" />
          <div className="h-4 w-2/3 bg-border rounded mb-2" />
          <div className="h-4 w-1/3 bg-border rounded" />
        </div>
      </div>
    </div>
  )
}
