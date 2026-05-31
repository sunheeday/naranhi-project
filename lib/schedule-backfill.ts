import type { Locale } from '@/lib/i18n'
import type { Database, Json } from '@/types/database'
import { createSupabaseServiceClient } from '@/lib/supabase/server'

type ServiceClient = ReturnType<typeof createSupabaseServiceClient>
type NoticeRow = Database['public']['Tables']['notices']['Row']
type TranslationRow = Database['public']['Tables']['notice_ai_translations']['Row']
type ScheduleInsert = Database['public']['Tables']['schedules']['Insert']

export async function backfillSchedulesForChild({
  serviceClient,
  schoolId,
  childId,
  preferredLocale,
}: {
  serviceClient: ServiceClient
  schoolId: string
  childId: string
  preferredLocale: Locale
}) {
  const { data: notices, error: noticeError } = await serviceClient
    .from('notices')
    .select('id,title,school_id')
    .eq('school_id', schoolId)
    .limit(200)

  if (noticeError) {
    throw new Error('기존 공지 조회 실패: ' + noticeError.message)
  }

  const noticeRows = (notices ?? []) as Pick<NoticeRow, 'id' | 'title' | 'school_id'>[]
  const noticeIds = noticeRows.map(notice => notice.id)
  if (noticeIds.length === 0) return

  const { data: translations, error: translationError } = await serviceClient
    .from('notice_ai_translations')
    .select('notice_id,target_language,translated_text,source_hard_facts,target_hard_facts,metadata,validation_status')
    .in('notice_id', noticeIds)
    .neq('validation_status', 'failed')

  if (translationError) {
    throw new Error('기존 번역 조회 실패: ' + translationError.message)
  }

  const chosen = chooseTranslationsByNotice(
    (translations ?? []) as Pick<
      TranslationRow,
      'notice_id' | 'target_language' | 'translated_text' | 'source_hard_facts' | 'target_hard_facts' | 'metadata' | 'validation_status'
    >[],
    preferredLocale,
  )
  if (chosen.size === 0) return

  const { data: existingSchedules, error: existingError } = await serviceClient
    .from('schedules')
    .select('notice_id,event_date')
    .eq('child_id', childId)
    .in('notice_id', Array.from(chosen.keys()))

  if (existingError) {
    throw new Error('기존 일정 조회 실패: ' + existingError.message)
  }

  const existingKeys = new Set(
    (existingSchedules ?? []).map(row => `${row.notice_id}:${row.event_date}`),
  )

  const noticeById = new Map(noticeRows.map(notice => [notice.id, notice]))
  const rows: ScheduleInsert[] = []
  for (const [noticeId, translation] of chosen.entries()) {
    const notice = noticeById.get(noticeId)
    if (!notice) continue

    const eventDates = scheduleDatesFromTranslation(translation)
    if (eventDates.length === 0) continue

    const title =
      optionalString(jsonObject(translation.metadata)?.title)
      ?? optionalString(notice.title)
      ?? '학교 일정'
    const location = scheduleLocationFromTranslation(translation)
    const description =
      optionalString(jsonObject(translation.metadata)?.summary_target_language)
      ?? optionalString(translation.translated_text)
      ?? title

    for (const eventDate of eventDates) {
      const key = `${noticeId}:${eventDate}`
      if (existingKeys.has(key)) continue
      existingKeys.add(key)
      rows.push({
        notice_id: noticeId,
        child_id: childId,
        title,
        event_date: eventDate,
        location,
        description,
      })
    }
  }

  if (rows.length === 0) return

  const { error: insertError } = await serviceClient
    .from('schedules')
    .insert(rows)

  if (insertError) {
    throw new Error('기존 일정 생성 실패: ' + insertError.message)
  }
}

export async function backfillSchedulesForChildren({
  serviceClient,
  children,
  preferredLocale,
}: {
  serviceClient: ServiceClient
  children: Array<{ id: string; school_id: string | null }>
  preferredLocale: Locale
}) {
  for (const child of children) {
    if (!child.school_id) continue
    await backfillSchedulesForChild({
      serviceClient,
      schoolId: child.school_id,
      childId: child.id,
      preferredLocale,
    })
  }
}

function chooseTranslationsByNotice(
  rows: Pick<
    TranslationRow,
    'notice_id' | 'target_language' | 'translated_text' | 'source_hard_facts' | 'target_hard_facts' | 'metadata' | 'validation_status'
  >[],
  preferredLocale: Locale,
) {
  const selected = new Map<string, typeof rows[number]>()

  for (const row of rows) {
    if (!optionalString(row.translated_text)) continue
    const current = selected.get(row.notice_id)
    if (!current) {
      selected.set(row.notice_id, row)
      continue
    }
    if (row.target_language === preferredLocale && current.target_language !== preferredLocale) {
      selected.set(row.notice_id, row)
      continue
    }
    if (
      row.validation_status === 'passed'
      && current.validation_status !== 'passed'
    ) {
      selected.set(row.notice_id, row)
    }
  }

  return selected
}

function scheduleDatesFromTranslation(
  translation: Pick<TranslationRow, 'source_hard_facts' | 'target_hard_facts'>,
) {
  const sourceFacts = hardFacts(translation.source_hard_facts)
  const targetFacts = hardFacts(translation.target_hard_facts)
  const values = [
    ...normalizedIsoDates(targetFacts.dates),
    ...normalizedIsoDates(targetFacts.deadlines),
    ...normalizedIsoDates(sourceFacts.dates),
    ...normalizedIsoDates(sourceFacts.deadlines),
  ]
  return Array.from(new Set(values))
}

function scheduleLocationFromTranslation(
  translation: Pick<TranslationRow, 'source_hard_facts' | 'target_hard_facts'>,
) {
  const sourceFacts = hardFacts(translation.source_hard_facts)
  const targetFacts = hardFacts(translation.target_hard_facts)
  return firstValue(targetFacts.locations) ?? firstValue(sourceFacts.locations)
}

function hardFacts(value: Json | null | undefined): Record<string, Json | undefined> {
  const root = jsonObject(value)
  const facts = jsonObject(root?.hard_facts)
  return facts ?? {}
}

function normalizedIsoDates(value: Json | undefined): string[] {
  if (!Array.isArray(value)) return []
  const results: string[] = []
  for (const item of value) {
    const text = machineVerifiableValue(item)
    if (!text) continue
    const matches = text.match(/\b\d{4}-\d{2}-\d{2}\b/g)
    if (matches?.length) {
      results.push(...matches)
    }
  }
  return results
}

function firstValue(value: Json | undefined): string | null {
  if (!Array.isArray(value)) return null
  for (const item of value) {
    const text = machineVerifiableValue(item)
    if (text) return text
  }
  return null
}

function machineVerifiableValue(value: Json): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value.map(machineVerifiableValue).filter(Boolean).join(' ').trim()
  }
  const obj = value as Record<string, Json>
  for (const key of ['normalized', 'value', 'raw_text', 'text']) {
    const item = obj[key]
    if (item !== undefined && item !== null) {
      return machineVerifiableValue(item)
    }
  }
  return Object.keys(obj)
    .sort()
    .map(key => machineVerifiableValue(obj[key]))
    .filter(Boolean)
    .join(' ')
    .trim()
}

function jsonObject(value: Json | null | undefined): Record<string, Json> | null {
  if (!value || Array.isArray(value) || typeof value !== 'object') return null
  return value as Record<string, Json>
}

function optionalString(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}
