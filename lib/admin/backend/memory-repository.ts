/**
 * 인메모리 어드민 저장소.
 *
 * 서버 프로세스 메모리에 데이터를 보관한다. DB 없이도 실제 API 흐름(등록/조회/삭제)을
 * 그대로 체험할 수 있게 하는 기본 구현이다. 서버를 재시작하면 시드 상태로 돌아간다.
 *
 * Next.js 개발 서버의 HMR(핫 리로드)로 모듈이 다시 평가돼도 데이터가 유지되도록
 * globalThis에 싱글턴을 보관한다.
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
import { seedData, genId, type AdminRepository } from './repository'

const STORE_KEY = Symbol.for('naranhi.admin.memoryStore')

type GlobalWithStore = typeof globalThis & { [STORE_KEY]?: AdminData }

function store(): AdminData {
  const g = globalThis as GlobalWithStore
  if (!g[STORE_KEY]) {
    g[STORE_KEY] = seedData()
  }
  return g[STORE_KEY]!
}

export class MemoryAdminRepository implements AdminRepository {
  async getOverview(): Promise<AdminData> {
    const s = store()
    return {
      notices: [...s.notices],
      events: [...s.events],
      messages: [...s.messages],
    }
  }

  async listNotices(): Promise<AdminNotice[]> {
    return [...store().notices]
  }

  async createNotice(input: NoticeInput): Promise<AdminNotice> {
    const notice: AdminNotice = { ...input, id: genId('ntc'), createdAt: new Date().toISOString() }
    store().notices.unshift(notice)
    return notice
  }

  async setNoticePinned(id: string, pinned: boolean): Promise<AdminNotice | null> {
    const notice = store().notices.find((n) => n.id === id)
    if (!notice) return null
    notice.pinned = pinned
    return notice
  }

  async deleteNotice(id: string): Promise<boolean> {
    const s = store()
    const before = s.notices.length
    s.notices = s.notices.filter((n) => n.id !== id)
    return s.notices.length < before
  }

  async listEvents(): Promise<AdminEvent[]> {
    return [...store().events]
  }

  async createEvent(input: EventInput): Promise<AdminEvent> {
    const event: AdminEvent = { ...input, id: genId('evt'), createdAt: new Date().toISOString() }
    store().events.unshift(event)
    return event
  }

  async deleteEvent(id: string): Promise<boolean> {
    const s = store()
    const before = s.events.length
    s.events = s.events.filter((e) => e.id !== id)
    return s.events.length < before
  }

  async listMessages(): Promise<AdminMessage[]> {
    return [...store().messages]
  }

  async createMessage(input: MessageInput): Promise<AdminMessage> {
    const message: AdminMessage = { ...input, id: genId('msg'), sentAt: new Date().toISOString() }
    store().messages.unshift(message)
    return message
  }

  async deleteMessage(id: string): Promise<boolean> {
    const s = store()
    const before = s.messages.length
    s.messages = s.messages.filter((m) => m.id !== id)
    return s.messages.length < before
  }

  async reset(): Promise<AdminData> {
    const g = globalThis as GlobalWithStore
    g[STORE_KEY] = seedData()
    return this.getOverview()
  }
}
