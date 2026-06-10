import type { Locale } from '@/lib/i18n'
import type { Json } from '@/types/database'

type NoticeTitleSource = {
  title: string | null
  extracted_content: Json | null
  translated_titles?: Record<string, string> | null
}

function jsonObject(value: Json | null | undefined): Record<string, Json> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function jsonString(value: Json | undefined): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function cleanTitle(value: string, maxLength: number): string {
  return value
    .replace(/^\s{0,3}#{1,6}\s+/, '')
    .trim()
    .slice(0, maxLength)
}

export function summaryTranslationFirstLine(
  extracted: Json | null | undefined,
  locale: Locale,
): string | null {
  const extractedObj = jsonObject(extracted)
  const summary = jsonObject(extractedObj.summary)
  if (locale === 'ko') {
    const rendered = jsonString(summary.rendered)
    if (!rendered) return null
    return rendered.split('\n')[0].trim().slice(0, 60) || null
  }
  const translations = jsonObject(summary.translations)
  const localized = jsonString(translations[locale])
  if (!localized) return null
  return localized.split('\n')[0].trim().slice(0, 60) || null
}

export function pickNoticeDisplayTitle(
  row: NoticeTitleSource,
  locale: Locale,
  fallbackTitle: string,
): string {
  if (locale === 'ko') {
    if (row.title && row.title.trim()) return cleanTitle(row.title, 60)
    const koSummaryTitle = summaryTranslationFirstLine(row.extracted_content, 'ko')
    if (koSummaryTitle) return cleanTitle(koSummaryTitle, 60)
    return fallbackTitle
  }

  const localizedTitle = row.translated_titles?.[locale]?.trim()
  if (localizedTitle) return cleanTitle(localizedTitle, 60)

  const localizedSummaryTitle = summaryTranslationFirstLine(row.extracted_content, locale)
  if (localizedSummaryTitle) return cleanTitle(localizedSummaryTitle, 60)

  if (row.title && row.title.trim()) return cleanTitle(row.title, 60)
  return fallbackTitle
}
