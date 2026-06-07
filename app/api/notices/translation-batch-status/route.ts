import { NextResponse, type NextRequest } from 'next/server'
import { isValidLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'

interface RequestBody {
  noticeIds?: unknown
  targetLanguage?: unknown
}

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const body = (await request.json().catch(() => ({}))) as RequestBody
  const targetLanguage = typeof body.targetLanguage === 'string' ? body.targetLanguage : ''
  if (!isValidLocale(targetLanguage)) {
    return NextResponse.json({ ok: false, error: 'invalid_target_language' }, { status: 400 })
  }

  const noticeIds = Array.isArray(body.noticeIds)
    ? Array.from(new Set(body.noticeIds.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)))
    : []
  if (noticeIds.length === 0) {
    return NextResponse.json({
      ok: true,
      targetLanguage,
      total: 0,
      completedCount: 0,
      pendingCount: 0,
      complete: true,
      pendingNoticeIds: [],
    })
  }

  const { data: rows, error } = await supabase
    .from('notice_ai_translations')
    .select('notice_id, translated_text, validation_status')
    .eq('target_language', targetLanguage)
    .in('notice_id', noticeIds)

  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 })
  }

  const bodyCompletedIds = new Set(
    (rows ?? [])
      .filter(row => row.translated_text)
      .map(row => row.notice_id)
      .filter((value): value is string => typeof value === 'string' && value.length > 0)
  )

  const { data: noticeRows, error: noticeError } = await supabase
    .from('notices')
    .select('id, extracted_content')
    .in('id', noticeIds)

  if (noticeError) {
    return NextResponse.json({ ok: false, error: noticeError.message }, { status: 500 })
  }

  const hasCompleteSourceTranslationsByNotice = new Map<string, boolean>()
  for (const row of noticeRows ?? []) {
    const noticeId = typeof row.id === 'string' ? row.id : ''
    if (!noticeId) continue
    hasCompleteSourceTranslationsByNotice.set(
      noticeId,
      hasCompleteTranslatedSources(row.extracted_content, targetLanguage),
    )
  }

  const { data: cardRows, error: cardError } = await supabase
    .from('notice_cards')
    .select('id, notice_id')
    .in('notice_id', noticeIds)

  if (cardError) {
    return NextResponse.json({ ok: false, error: cardError.message }, { status: 500 })
  }

  const cardIds = (cardRows ?? [])
    .map(row => row.id)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)

  const { data: translatedCardRows, error: translatedCardError } = cardIds.length === 0
    ? { data: [], error: null }
    : await supabase
        .from('notice_card_translations')
        .select('notice_card_id')
        .eq('target_language', targetLanguage)
        .in('notice_card_id', cardIds)

  if (translatedCardError) {
    return NextResponse.json({ ok: false, error: translatedCardError.message }, { status: 500 })
  }

  const translatedCardIds = new Set(
    (translatedCardRows ?? [])
      .map(row => row.notice_card_id)
      .filter((value): value is string => typeof value === 'string' && value.length > 0)
  )

  const cardIdsByNotice = new Map<string, string[]>()
  for (const row of cardRows ?? []) {
    const noticeId = typeof row.notice_id === 'string' ? row.notice_id : ''
    const cardId = typeof row.id === 'string' ? row.id : ''
    if (!noticeId || !cardId) continue
    const bucket = cardIdsByNotice.get(noticeId)
    if (bucket) {
      bucket.push(cardId)
    } else {
      cardIdsByNotice.set(noticeId, [cardId])
    }
  }

  const completedIds = new Set(
    noticeIds.filter(noticeId => {
      if (!bodyCompletedIds.has(noticeId)) {
        return false
      }
      const perNoticeCardIds = cardIdsByNotice.get(noticeId) ?? []
      if (!(perNoticeCardIds.length === 0 || perNoticeCardIds.every(cardId => translatedCardIds.has(cardId)))) {
        return false
      }
      return hasCompleteSourceTranslationsByNotice.get(noticeId) ?? true
    })
  )

  const pendingNoticeIds = noticeIds.filter(noticeId => !completedIds.has(noticeId))

  return NextResponse.json({
    ok: true,
    targetLanguage,
    total: noticeIds.length,
    completedCount: completedIds.size,
    pendingCount: pendingNoticeIds.length,
    complete: pendingNoticeIds.length === 0,
    pendingNoticeIds,
  })
}

function hasCompleteTranslatedSources(extracted: unknown, locale: string): boolean {
  if (locale === 'ko' || !extracted || typeof extracted !== 'object') {
    return true
  }

  const extractedRecord = extracted as Record<string, unknown>
  const summary = asRecord(extractedRecord.summary)
  const summaryRendered = typeof summary?.rendered === 'string' ? summary.rendered.trim() : ''
  if (summaryRendered) {
    const summaryTranslations = asRecord(summary?.translations)
    const localizedSummary = typeof summaryTranslations?.[locale] === 'string'
      ? summaryTranslations[locale].trim()
      : ''
    if (!localizedSummary) {
      return false
    }
  }

  const sources = Array.isArray(extractedRecord.sources) ? extractedRecord.sources : []
  for (const source of sources) {
    const sourceRecord = asRecord(source)
    const refinedText = typeof sourceRecord?.refined_text === 'string' ? sourceRecord.refined_text.trim() : ''
    if (!refinedText) continue
    const translations = asRecord(sourceRecord?.translations)
    const localized = typeof translations?.[locale] === 'string' ? translations[locale].trim() : ''
    if (!localized) {
      return false
    }
  }

  return true
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}
