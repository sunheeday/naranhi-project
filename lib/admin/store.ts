'use client'

/**
 * 어드민 클라이언트 스토어.
 *
 * 백엔드 API(/api/admin/*)를 데이터 소스로 사용한다. 여러 페이지가 마운트돼 있어도
 * 하나의 캐시를 구독(pub/sub)해 화면이 서로 동기화된다.
 *
 * 쓰기 작업은 낙관적 업데이트(optimistic update) 후 서버 응답으로 재검증(refetch)한다.
 * 덕분에 "등록 → 목록으로 이동" 시 새 항목이 즉시 보이면서도 서버 상태와 일치한다.
 *
 * 표시용 타입/라벨/유틸은 프레임워크 중립 모듈(lib/admin/types)에서 그대로 재노출한다.
 */

import { useCallback, useEffect, useSyncExternalStore } from 'react'
import type {
  AdminData,
  AdminNotice,
  AdminEvent,
  AdminMessage,
  NoticeInput,
  EventInput,
  MessageInput,
} from '@/lib/admin/types'
import * as api from '@/lib/admin/api-client'

export * from '@/lib/admin/types'

const EMPTY: AdminData = { notices: [], events: [], messages: [] }

let cache: AdminData = EMPTY
let loaded = false
let loading = false
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

function setCache(next: AdminData) {
  cache = next
  emit()
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

function getSnapshot(): AdminData {
  return cache
}

function getServerSnapshot(): AdminData {
  return EMPTY
}

async function refetch() {
  try {
    const data = await api.fetchOverview()
    loaded = true
    setCache(data)
  } catch {
    // 네트워크 오류 시 기존 캐시를 유지한다.
  }
}

function ensureLoaded() {
  if (loaded || loading) return
  loading = true
  refetch().finally(() => {
    loading = false
  })
}

/** 낙관적 업데이트 적용 → 서버 호출 → 재검증(실패 시에도 재검증으로 정합성 회복) */
async function mutate(optimistic: (d: AdminData) => AdminData, call: () => Promise<unknown>) {
  const rollback = cache
  setCache(optimistic(cache))
  try {
    await call()
  } catch {
    setCache(rollback)
  } finally {
    await refetch()
  }
}

function tempId(prefix: string): string {
  return `tmp_${prefix}_${Date.now().toString(36)}`
}

export function useAdminData(): AdminData {
  const data = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  useEffect(() => {
    ensureLoaded()
  }, [])
  return data
}

export function useAdminActions() {
  const addNotice = useCallback((input: NoticeInput) => {
    const optimisticItem: AdminNotice = { ...input, id: tempId('ntc'), createdAt: new Date().toISOString() }
    return mutate(
      (d) => ({ ...d, notices: [optimisticItem, ...d.notices] }),
      () => api.createNotice(input),
    )
  }, [])

  const deleteNotice = useCallback((id: string) => {
    return mutate(
      (d) => ({ ...d, notices: d.notices.filter((n) => n.id !== id) }),
      () => api.deleteNotice(id),
    )
  }, [])

  const togglePin = useCallback((id: string) => {
    const current = cache.notices.find((n) => n.id === id)
    const nextPinned = !current?.pinned
    return mutate(
      (d) => ({ ...d, notices: d.notices.map((n) => (n.id === id ? { ...n, pinned: nextPinned } : n)) }),
      () => api.setNoticePinned(id, nextPinned),
    )
  }, [])

  const addEvent = useCallback((input: EventInput) => {
    const optimisticItem: AdminEvent = { ...input, id: tempId('evt'), createdAt: new Date().toISOString() }
    return mutate(
      (d) => ({ ...d, events: [optimisticItem, ...d.events] }),
      () => api.createEvent(input),
    )
  }, [])

  const deleteEvent = useCallback((id: string) => {
    return mutate(
      (d) => ({ ...d, events: d.events.filter((e) => e.id !== id) }),
      () => api.deleteEvent(id),
    )
  }, [])

  const addMessage = useCallback((input: MessageInput) => {
    const optimisticItem: AdminMessage = { ...input, id: tempId('msg'), sentAt: new Date().toISOString() }
    return mutate(
      (d) => ({ ...d, messages: [optimisticItem, ...d.messages] }),
      () => api.createMessage(input),
    )
  }, [])

  const deleteMessage = useCallback((id: string) => {
    return mutate(
      (d) => ({ ...d, messages: d.messages.filter((m) => m.id !== id) }),
      () => api.deleteMessage(id),
    )
  }, [])

  const resetDemo = useCallback(async () => {
    try {
      const data = await api.resetDemo()
      loaded = true
      setCache(data)
    } catch {
      await refetch()
    }
  }, [])

  return { addNotice, deleteNotice, togglePin, addEvent, deleteEvent, addMessage, deleteMessage, resetDemo }
}
