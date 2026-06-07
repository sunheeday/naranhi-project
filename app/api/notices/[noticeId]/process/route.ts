import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'

interface RouteContext {
  params: Promise<{ noticeId: string }>
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { noticeId } = await context.params
  if (!noticeId) {
    return NextResponse.json({ ok: false, error: 'missing_notice_id' }, { status: 400 })
  }

  const supabase = await createSupabaseServerClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  }

  const { data: notice } = await supabase
    .from('notices')
    .select('id, status, extracted_content')
    .eq('id', noticeId)
    .maybeSingle()

  if (!notice) {
    return NextResponse.json({ ok: false, error: 'notice_not_found' }, { status: 404 })
  }

  const targetLanguage = await resolveTargetLanguage(request, user.id)
  if (targetLanguage === 'ko' && notice.status === 'done') {
    return NextResponse.json({ ok: true, skipped: true, status: notice.status, targetLanguage })
  }

  const { data: cachedTranslation } = await supabase
    .from('notice_ai_translations')
    .select('id, translated_text, validation_status')
    .eq('notice_id', noticeId)
    .eq('target_language', targetLanguage)
    .maybeSingle()

  if (
    cachedTranslation?.translated_text
    && await hasCompleteCardTranslationCache(supabase, noticeId, targetLanguage)
    && hasCompleteTranslatedSources(notice.extracted_content, targetLanguage)
  ) {
    return NextResponse.json({
      ok: true,
      skipped: true,
      status: notice.status,
      targetLanguage,
      translationStatus: cachedTranslation.validation_status,
    })
  }

  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')

  if (!apiBase) {
    return NextResponse.json({ ok: false, error: 'missing_fastapi_url' }, { status: 503 })
  }

  const response = await fetch(`${apiBase}/notices/${encodeURIComponent(noticeId)}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_language: targetLanguage, background: true }),
    cache: 'no-store',
  })

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    return NextResponse.json(
      { ok: false, error: body?.detail ?? body?.error ?? 'notice_process_failed' },
      { status: response.status }
    )
  }

  return NextResponse.json(
    { ok: true, targetLanguage, accepted: body?.accepted ?? true, result: body },
    { status: response.status }
  )
}

async function hasCompleteCardTranslationCache(
  supabase: Awaited<ReturnType<typeof createSupabaseServerClient>>,
  noticeId: string,
  targetLanguage: Locale,
): Promise<boolean> {
  if (targetLanguage === 'ko') {
    return true
  }

  const { data: cards } = await supabase
    .from('notice_cards')
    .select('id')
    .eq('notice_id', noticeId)

  const cardIds = (cards ?? [])
    .map(card => card.id)
    .filter((value): value is string => typeof value === 'string' && value.length > 0)

  if (cardIds.length === 0) {
    return true
  }

  const { data: translatedCards } = await supabase
    .from('notice_card_translations')
    .select('notice_card_id')
    .eq('target_language', targetLanguage)
    .in('notice_card_id', cardIds)

  const translatedIds = new Set(
    (translatedCards ?? [])
      .map(row => row.notice_card_id)
      .filter((value): value is string => typeof value === 'string' && value.length > 0)
  )

  return cardIds.every(cardId => translatedIds.has(cardId))
}

async function resolveTargetLanguage(request: NextRequest, userId: string): Promise<Locale> {
  const body = await request.json().catch(() => null)
  if (isValidLocale(body?.target_language)) {
    return body.target_language
  }

  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  if (isValidLocale(cookieLocale)) {
    return cookieLocale
  }

  const supabase = await createSupabaseServerClient()
  const { data: profile } = await supabase
    .from('profiles')
    .select('native_language, locale')
    .eq('id', userId)
    .maybeSingle()

  if (isValidLocale(profile?.locale)) {
    return profile.locale
  }
  if (isValidLocale(profile?.native_language)) {
    return profile.native_language
  }

  return defaultLocale
}

function hasCompleteTranslatedSources(extracted: unknown, locale: Locale): boolean {
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
