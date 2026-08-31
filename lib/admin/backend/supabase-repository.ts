/**
 * Supabase 어드민 저장소 — "나중에 DB 연동" 레퍼런스 구현.
 *
 * 지금은 사용되지 않는다. 팩토리(`getAdminRepository`)가 환경변수 `ADMIN_BACKEND=supabase`일 때만
 * 이 구현을 선택한다. 기본값은 인메모리다.
 *
 * 연동 방법(요약):
 *   1) docs/admin-backend.md 의 마이그레이션 SQL로 admin_notices / admin_events / admin_messages 테이블 생성
 *   2) .env.local 에 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ADMIN_BACKEND=supabase 설정
 *   3) 서버 재시작 — API 라우트는 그대로 두고 저장소만 교체된다.
 *
 * 참고: 여기서는 생성된 Database 타입에 의존하지 않도록 "언타입" 클라이언트를 쓴다.
 * 실제 연동 후에는 `supabase gen types`로 타입을 재생성해 타입 안전성을 높이는 것을 권장한다.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import type {
  AdminData,
  AdminNotice,
  AdminEvent,
  AdminMessage,
  NoticeInput,
  EventInput,
  MessageInput,
  NoticeCategory,
  EventType,
  Audience,
} from '@/lib/admin/types'
import type { AdminRepository } from './repository'

function client(): SupabaseClient {
  const url = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) {
    throw new Error('Supabase 어드민 저장소에는 SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY가 필요합니다.')
  }
  // Database 제네릭을 생략해 admin_* 테이블을 자유롭게 참조할 수 있게 한다(타입 재생성 전).
  return createClient(url, key, { auth: { persistSession: false } })
}

// ─── DB row ↔ 도메인 매퍼 ─────────────────────────

function toNotice(row: any): AdminNotice {
  return {
    id: String(row.id),
    title: row.title ?? '',
    body: row.body ?? '',
    category: (row.category ?? 'notice') as NoticeCategory,
    audience: (row.audience ?? 'class') as Audience,
    pinned: Boolean(row.pinned),
    createdAt: row.created_at ?? new Date().toISOString(),
  }
}

function toEvent(row: any): AdminEvent {
  return {
    id: String(row.id),
    title: row.title ?? '',
    date: row.event_date ?? '',
    time: row.event_time ?? '',
    type: (row.type ?? 'event') as EventType,
    audience: (row.audience ?? 'class') as Audience,
    memo: row.memo ?? '',
    createdAt: row.created_at ?? new Date().toISOString(),
  }
}

function toMessage(row: any): AdminMessage {
  return {
    id: String(row.id),
    title: row.title ?? '',
    body: row.body ?? '',
    audience: (row.audience ?? 'all') as Audience,
    recipient: row.recipient ?? '',
    sentAt: row.sent_at ?? new Date().toISOString(),
  }
}

export class SupabaseAdminRepository implements AdminRepository {
  private db = client()

  async getOverview(): Promise<AdminData> {
    const [notices, events, messages] = await Promise.all([
      this.listNotices(),
      this.listEvents(),
      this.listMessages(),
    ])
    return { notices, events, messages }
  }

  async listNotices(): Promise<AdminNotice[]> {
    const { data, error } = await this.db
      .from('admin_notices')
      .select('*')
      .order('created_at', { ascending: false })
    if (error) throw error
    return (data ?? []).map(toNotice)
  }

  async createNotice(input: NoticeInput): Promise<AdminNotice> {
    const { data, error } = await this.db
      .from('admin_notices')
      .insert({
        title: input.title,
        body: input.body,
        category: input.category,
        audience: input.audience,
        pinned: input.pinned,
      })
      .select('*')
      .single()
    if (error) throw error
    return toNotice(data)
  }

  async setNoticePinned(id: string, pinned: boolean): Promise<AdminNotice | null> {
    const { data, error } = await this.db
      .from('admin_notices')
      .update({ pinned })
      .eq('id', id)
      .select('*')
      .maybeSingle()
    if (error) throw error
    return data ? toNotice(data) : null
  }

  async deleteNotice(id: string): Promise<boolean> {
    const { error, count } = await this.db
      .from('admin_notices')
      .delete({ count: 'exact' })
      .eq('id', id)
    if (error) throw error
    return (count ?? 0) > 0
  }

  async listEvents(): Promise<AdminEvent[]> {
    const { data, error } = await this.db
      .from('admin_events')
      .select('*')
      .order('event_date', { ascending: true })
    if (error) throw error
    return (data ?? []).map(toEvent)
  }

  async createEvent(input: EventInput): Promise<AdminEvent> {
    const { data, error } = await this.db
      .from('admin_events')
      .insert({
        title: input.title,
        event_date: input.date,
        event_time: input.time || null,
        type: input.type,
        audience: input.audience,
        memo: input.memo,
      })
      .select('*')
      .single()
    if (error) throw error
    return toEvent(data)
  }

  async deleteEvent(id: string): Promise<boolean> {
    const { error, count } = await this.db
      .from('admin_events')
      .delete({ count: 'exact' })
      .eq('id', id)
    if (error) throw error
    return (count ?? 0) > 0
  }

  async listMessages(): Promise<AdminMessage[]> {
    const { data, error } = await this.db
      .from('admin_messages')
      .select('*')
      .order('sent_at', { ascending: false })
    if (error) throw error
    return (data ?? []).map(toMessage)
  }

  async createMessage(input: MessageInput): Promise<AdminMessage> {
    const { data, error } = await this.db
      .from('admin_messages')
      .insert({
        title: input.title,
        body: input.body,
        audience: input.audience,
        recipient: input.recipient,
      })
      .select('*')
      .single()
    if (error) throw error
    return toMessage(data)
  }

  async deleteMessage(id: string): Promise<boolean> {
    const { error, count } = await this.db
      .from('admin_messages')
      .delete({ count: 'exact' })
      .eq('id', id)
    if (error) throw error
    return (count ?? 0) > 0
  }

  async reset(): Promise<AdminData> {
    // 운영 데이터를 시드로 되돌리지 않는다(안전). 현재 상태를 그대로 반환한다.
    return this.getOverview()
  }
}
