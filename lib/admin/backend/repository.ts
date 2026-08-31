/**
 * 어드민 데이터 접근 계층(Repository) 인터페이스.
 *
 * API 라우트 핸들러는 이 인터페이스에만 의존한다. 실제 저장소가 무엇인지(메모리/Supabase)는
 * `getAdminRepository()` 팩토리가 결정한다. 나중에 DB를 붙일 때는 Supabase 구현으로 교체만 하면 되고
 * 라우트 핸들러 코드는 바뀌지 않는다.
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

export interface AdminRepository {
  getOverview(): Promise<AdminData>

  listNotices(): Promise<AdminNotice[]>
  createNotice(input: NoticeInput): Promise<AdminNotice>
  setNoticePinned(id: string, pinned: boolean): Promise<AdminNotice | null>
  deleteNotice(id: string): Promise<boolean>

  listEvents(): Promise<AdminEvent[]>
  createEvent(input: EventInput): Promise<AdminEvent>
  deleteEvent(id: string): Promise<boolean>

  listMessages(): Promise<AdminMessage[]>
  createMessage(input: MessageInput): Promise<AdminMessage>
  deleteMessage(id: string): Promise<boolean>

  /** 데모 데이터를 시드 상태로 되돌린다(메모리 구현 전용, 실서비스에서는 no-op 가능). */
  reset(): Promise<AdminData>
}

// ─── 시드 데이터 ──────────────────────────────────

function daysAgoIso(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString()
}

function daysFromNowDate(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** 첫 실행 시 화면이 비어 보이지 않도록 하는 예시 데이터. */
export function seedData(): AdminData {
  return {
    notices: [
      {
        id: 'seed-n1',
        title: '9월 현장체험학습 안내 및 참가 동의서 제출',
        body:
          '9월 18일(목) 서울대공원으로 현장체험학습을 다녀옵니다.\n\n· 준비물: 도시락, 물, 간식, 우산\n· 복장: 편한 운동화와 활동복\n· 참가 동의서는 9월 12일(금)까지 제출해 주세요.\n\n안전한 체험학습이 되도록 협조 부탁드립니다.',
        category: 'letter',
        audience: 'class',
        pinned: true,
        createdAt: daysAgoIso(1),
      },
      {
        id: 'seed-n2',
        title: '10월 방과후학교 수강 신청 안내',
        body:
          '10월 방과후학교 수강 신청을 받습니다.\n개설 강좌와 시간표는 첨부된 안내문을 확인해 주세요.\n신청 기간: 9월 22일(월) ~ 9월 26일(금)',
        category: 'notice',
        audience: 'all',
        pinned: false,
        createdAt: daysAgoIso(3),
      },
      {
        id: 'seed-n3',
        title: '이번 주 급식 식단표 (9/1 ~ 9/5)',
        body: '이번 주 급식 식단표를 안내드립니다. 알레르기 유발 식재료가 포함될 수 있으니 참고 바랍니다.',
        category: 'meal',
        audience: 'all',
        pinned: false,
        createdAt: daysAgoIso(5),
      },
    ],
    events: [
      {
        id: 'seed-e1',
        title: '현장체험학습 (서울대공원)',
        date: daysFromNowDate(19),
        time: '09:00',
        type: 'event',
        audience: 'class',
        memo: '도시락·물·간식 준비',
        createdAt: daysAgoIso(1),
      },
      {
        id: 'seed-e2',
        title: '참가 동의서 제출 마감',
        date: daysFromNowDate(13),
        time: '',
        type: 'deadline',
        audience: 'class',
        memo: '현장체험학습 동의서',
        createdAt: daysAgoIso(1),
      },
      {
        id: 'seed-e3',
        title: '2학기 중간 수학 단원평가',
        date: daysFromNowDate(26),
        time: '10:00',
        type: 'exam',
        audience: 'class',
        memo: '3~5단원 범위',
        createdAt: daysAgoIso(2),
      },
    ],
    messages: [
      {
        id: 'seed-m1',
        title: '내일 준비물 안내',
        body: '안녕하세요, 내일은 미술 시간이 있어 물감과 붓이 필요합니다. 준비 부탁드려요.',
        audience: 'all',
        recipient: '전체 학부모',
        sentAt: daysAgoIso(2),
      },
      {
        id: 'seed-m2',
        title: '독서록 제출 관련',
        body: '민준이 이번 주 독서록이 아직 제출되지 않았습니다. 확인 부탁드립니다.',
        audience: 'class',
        recipient: '이민준 학부모',
        sentAt: daysAgoIso(4),
      },
    ],
  }
}

export function genId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`
}
