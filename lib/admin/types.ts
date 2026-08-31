/**
 * 학교(선생님) 어드민 도메인 타입과 표시용 유틸.
 *
 * 프레임워크 중립(서버/클라이언트 공용) 모듈이다. React나 'use client'에 의존하지 않으므로
 * API 라우트 핸들러, repository 구현, 클라이언트 컴포넌트 어디서든 import할 수 있다.
 */

export type NoticeCategory = 'letter' | 'notice' | 'meal' | 'event'
export type EventType = 'event' | 'exam' | 'deadline' | 'holiday'
export type Audience = 'all' | 'class'

export interface AdminNotice {
  id: string
  title: string
  body: string
  category: NoticeCategory
  audience: Audience
  pinned: boolean
  createdAt: string
}

export interface AdminEvent {
  id: string
  title: string
  date: string // YYYY-MM-DD
  time: string // HH:MM or ''
  type: EventType
  audience: Audience
  memo: string
  createdAt: string
}

export interface AdminMessage {
  id: string
  title: string
  body: string
  audience: Audience
  recipient: string
  sentAt: string
}

export interface AdminData {
  notices: AdminNotice[]
  events: AdminEvent[]
  messages: AdminMessage[]
}

/** 생성 입력(서버가 id·시간을 채운다) */
export type NoticeInput = Omit<AdminNotice, 'id' | 'createdAt'>
export type EventInput = Omit<AdminEvent, 'id' | 'createdAt'>
export type MessageInput = Omit<AdminMessage, 'id' | 'sentAt'>

/**
 * 데모 교사 프로필.
 * 실제 연동 시에는 로그인한 교사 계정 → 담당 학교/학급 정보로 대체한다.
 */
export const TEACHER_PROFILE = {
  teacherName: '김나란 선생님',
  school: '부천북초등학교',
  grade: 3,
  classNo: 2,
} as const

export const CLASS_LABEL = `${TEACHER_PROFILE.grade}학년 ${TEACHER_PROFILE.classNo}반`

// ─── 표시용 라벨/유틸 ──────────────────────────────

export const NOTICE_CATEGORY_LABEL: Record<NoticeCategory, string> = {
  letter: '가정통신문',
  notice: '알림',
  meal: '급식',
  event: '행사',
}

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  event: '행사',
  exam: '시험',
  deadline: '제출 마감',
  holiday: '방학·휴일',
}

export const AUDIENCE_LABEL: Record<Audience, string> = {
  all: '전체 학부모',
  class: CLASS_LABEL,
}

export const NOTICE_CATEGORIES: NoticeCategory[] = ['letter', 'notice', 'meal', 'event']
export const EVENT_TYPES: EventType[] = ['event', 'exam', 'deadline', 'holiday']
export const AUDIENCES: Audience[] = ['all', 'class']

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '방금 전'
  if (mins < 60) return `${mins}분 전`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}시간 전`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}일 전`
  return new Date(iso).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })
}

export function formatEventDate(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  const dt = new Date(y, (m ?? 1) - 1, d ?? 1)
  const weekday = ['일', '월', '화', '수', '목', '금', '토'][dt.getDay()]
  return `${m}월 ${d}일 (${weekday})`
}

export function dDayLabel(date: string): { text: string; urgent: boolean } {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const [y, m, d] = date.split('-').map(Number)
  const target = new Date(y, (m ?? 1) - 1, d ?? 1)
  const days = Math.round((target.getTime() - today.getTime()) / 86400000)
  if (days === 0) return { text: 'D-DAY', urgent: true }
  if (days < 0) return { text: `${-days}일 지남`, urgent: false }
  return { text: `D-${days}`, urgent: days <= 3 }
}
