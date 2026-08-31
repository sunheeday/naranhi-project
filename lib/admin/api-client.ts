'use client'

/**
 * 어드민 API 클라이언트.
 * 프런트엔드는 저장소 구현을 알 필요 없이 이 함수들로 백엔드(/api/admin/*)와 통신한다.
 */

import type {
  AdminData,
  AdminNotice,
  AdminEvent,
  AdminMessage,
  NoticeInput,
  EventInput,
  MessageInput,
} from '@/lib/admin/types'

interface ApiOk<T> {
  ok: true
  data: T
}
interface ApiErr {
  ok: false
  error: string
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    cache: 'no-store',
  })
  const json = (await res.json().catch(() => null)) as ApiOk<T> | ApiErr | null
  if (!json || json.ok !== true) {
    throw new Error((json as ApiErr | null)?.error ?? `요청 실패 (${res.status})`)
  }
  return json.data
}

export function fetchOverview(): Promise<AdminData> {
  return request<AdminData>('/api/admin/overview')
}

export function createNotice(input: NoticeInput): Promise<AdminNotice> {
  return request<AdminNotice>('/api/admin/notices', { method: 'POST', body: JSON.stringify(input) })
}

export function setNoticePinned(id: string, pinned: boolean): Promise<AdminNotice> {
  return request<AdminNotice>(`/api/admin/notices/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ pinned }),
  })
}

export function deleteNotice(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/admin/notices/${id}`, { method: 'DELETE' })
}

export function createEvent(input: EventInput): Promise<AdminEvent> {
  return request<AdminEvent>('/api/admin/events', { method: 'POST', body: JSON.stringify(input) })
}

export function deleteEvent(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/admin/events/${id}`, { method: 'DELETE' })
}

export function createMessage(input: MessageInput): Promise<AdminMessage> {
  return request<AdminMessage>('/api/admin/messages', { method: 'POST', body: JSON.stringify(input) })
}

export function deleteMessage(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/admin/messages/${id}`, { method: 'DELETE' })
}

export function resetDemo(): Promise<AdminData> {
  return request<AdminData>('/api/admin/reset', { method: 'POST' })
}
