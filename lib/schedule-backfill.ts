import type { Locale } from '@/lib/i18n'
import type { Database, Json } from '@/types/database'
import { createSupabaseServiceClient } from '@/lib/supabase/server'

type ServiceClient = ReturnType<typeof createSupabaseServiceClient>
type NoticeRow = Database['public']['Tables']['notices']['Row']
type SchoolEventInsert = Database['public']['Tables']['school_events']['Insert']
type NoticeCardRow = Pick<Database['public']['Tables']['notice_cards']['Row'], 'notice_id' | 'type' | 'content'>

export async function backfillSchoolEventsForSchool({
  serviceClient,
  schoolId,
  preferredLocale: _preferredLocale,
}: {
  serviceClient: ServiceClient
  schoolId: string
  preferredLocale: Locale
}) {
  const { data: notices, error: noticeError } = await serviceClient
    .from('notices')
    .select('id,title,original_text,school_id,event_dates,event_location,created_at')
    .eq('school_id', schoolId)
    .order('created_at', { ascending: false })

  if (noticeError) {
    throw new Error('기존 공지 조회 실패: ' + noticeError.message)
  }

  const noticeRows = (notices ?? []) as Pick<
    NoticeRow,
    'id' | 'title' | 'original_text' | 'school_id' | 'event_dates' | 'event_location' | 'created_at'
  >[]
  const noticeIds = noticeRows.map(notice => notice.id)
  if (noticeIds.length === 0) return

  const { data: existingEvents, error: existingError } = await serviceClient
    .from('school_events')
    .select('notice_id,event_date')
    .eq('school_id', schoolId)
    .in('notice_id', noticeIds)

  if (existingError) {
    throw new Error('기존 학교 일정 조회 실패: ' + existingError.message)
  }

  const existingKeys = new Set(
    (existingEvents ?? []).map(row => `${row.notice_id}:${row.event_date}`),
  )
  const { data: noticeCards, error: cardError } = await serviceClient
    .from('notice_cards')
    .select('notice_id,type,content')
    .in('notice_id', noticeIds)
    .eq('type', 'schedule')

  if (cardError) {
    throw new Error('기존 일정 카드 조회 실패: ' + cardError.message)
  }

  const scheduleCardsByNoticeId = new Map<string, NoticeCardRow[]>()
  for (const row of (noticeCards ?? []) as NoticeCardRow[]) {
    const list = scheduleCardsByNoticeId.get(row.notice_id) ?? []
    list.push(row)
    scheduleCardsByNoticeId.set(row.notice_id, list)
  }

  const rows: SchoolEventInsert[] = []
  for (const notice of noticeRows) {
    const eventDates = noticeEventDates(notice.event_dates).length > 0
      ? noticeEventDates(notice.event_dates)
      : parseScheduleCardDates(scheduleCardsByNoticeId.get(notice.id) ?? [])
    if (eventDates.length === 0) continue

    const title = optionalString(notice.title) ?? '학교 일정'
    const scheduleCardLocation = parseScheduleCardLocation(scheduleCardsByNoticeId.get(notice.id) ?? [])
    const description = firstNonEmptyLine(notice.original_text) ?? title

    for (const eventDate of eventDates) {
      const key = `${notice.id}:${eventDate}`
      if (existingKeys.has(key)) continue
      existingKeys.add(key)
      rows.push({
        school_id: schoolId,
        notice_id: notice.id,
        title,
        event_date: eventDate,
        location: optionalString(notice.event_location) ?? scheduleCardLocation,
        description,
        source_language: 'ko',
      })
    }
  }

  if (rows.length === 0) return

  const { error: insertError } = await serviceClient
    .from('school_events')
    .insert(rows)

  if (insertError) {
    throw new Error('기존 학교 일정 생성 실패: ' + insertError.message)
  }
}

export async function backfillSchoolEventsForSchools({
  serviceClient,
  schoolIds,
  preferredLocale,
}: {
  serviceClient: ServiceClient
  schoolIds: string[]
  preferredLocale: Locale
}) {
  for (const schoolId of Array.from(new Set(schoolIds))) {
    await backfillSchoolEventsForSchool({
      serviceClient,
      schoolId,
      preferredLocale,
    })
  }
}

function noticeEventDates(value: Json): string[] {
  if (!Array.isArray(value)) return []
  return Array.from(new Set(
    value
      .filter((item): item is string => typeof item === 'string')
      .map(item => item.trim())
      .filter(item => /^\d{4}-\d{2}-\d{2}$/.test(item)),
  ))
}

function parseScheduleCardDates(rows: NoticeCardRow[]): string[] {
  const dates = new Set<string>()
  for (const row of rows) {
    const content = localizedCardContent(row.content)
    const items = cardItems(content)
    const legacyDate = asString(content?.date)
    for (const value of [
      ...items.flatMap(item => [item.text, item.hint]),
      legacyDate,
    ]) {
      for (const date of extractIsoDates(value)) {
        dates.add(date)
      }
    }
  }
  return Array.from(dates)
}

function parseScheduleCardLocation(rows: NoticeCardRow[]): string | null {
  for (const row of rows) {
    const content = localizedCardContent(row.content)
    const legacyLocation = asString(content?.location)
    if (legacyLocation) return legacyLocation
    for (const item of cardItems(content)) {
      const text = item.text.trim()
      if (text.startsWith('장소:')) {
        return text.slice(3).trim() || null
      }
    }
  }
  return null
}

function localizedCardContent(content: Json): Record<string, unknown> | null {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return null
  const object = content as Record<string, unknown>
  const localized = object.ko
  if (localized && typeof localized === 'object' && !Array.isArray(localized)) {
    return localized as Record<string, unknown>
  }
  return object
}

function cardItems(content: Record<string, unknown> | null): Array<{ text: string; hint: string | null }> {
  if (!content || !Array.isArray(content.items)) return []
  return content.items.flatMap(item => {
    if (typeof item === 'string') {
      return item.trim() ? [{ text: item.trim(), hint: null }] : []
    }
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const text = asString((item as Record<string, unknown>).text)
    if (!text) return []
    return [{
      text,
      hint: asString((item as Record<string, unknown>).hint),
    }]
  })
}

function extractIsoDates(value: string | null): string[] {
  if (!value) return []
  const matches = new Set<string>()
  for (const match of value.match(/\d{4}-\d{2}-\d{2}/g) ?? []) {
    matches.add(match)
  }
  const yearlessPatterns = [
    /(^|[^\d])(\d{1,2})\s*월\s*(\d{1,2})\s*일/g,
    /(^|[^\d])(\d{1,2})\s*[./]\s*(\d{1,2})(?:[./]|$)/g,
    /(^|[^\d])(\d{1,2})\s*\/\s*(\d{1,2})(?!\d)/g,
  ]
  for (const pattern of yearlessPatterns) {
    let match: RegExpExecArray | null
    while ((match = pattern.exec(value)) !== null) {
      const month = Number(match[2])
      const day = Number(match[3])
      if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
        matches.add(`2026-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`)
      }
    }
  }
  return Array.from(matches)
}

function firstNonEmptyLine(value: string | null | undefined): string | null {
  const text = optionalString(value)
  if (!text) return null
  const firstLine = text
    .split('\n')
    .map(line => line.trim())
    .find(Boolean)
  return firstLine ? firstLine.slice(0, 160) : null
}

function optionalString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function asString(value: unknown): string | null {
  return optionalString(value)
}
