/**
 * 다국어 번역 jsonb 헬퍼.
 *
 * notice_ai_translations는 언어별 row로 저장되고, notice_cards.content는
 * { [locale]: content } 형태의 jsonb로 저장된다. 화면에서는 필요한 값을
 * Record 형태로 모아 사용자 locale -> ko -> 첫 번째 키 순서로 fallback한다.
 *
 * Lazy 번역: 사용자 locale 키가 없으면 클라이언트가 /api/notices/[id]/translate 를
 * 호출해 Gemini로 즉시 번역 후 jsonb에 캐시한다.
 */

import type { Locale } from '@/lib/i18n'

export type Translations = Record<string, string>

/** 사용자 locale 우선, ko fallback, 마지막으로 첫 키. 없으면 null. */
export function pickTranslation(
  translations: Translations | null | undefined,
  locale: Locale,
): string | null {
  if (!translations) return null
  const v = translations[locale]
  if (typeof v === 'string' && v) return v
  if (typeof translations.ko === 'string' && translations.ko) return translations.ko
  for (const k of Object.keys(translations)) {
    const x = translations[k]
    if (typeof x === 'string' && x) return x
  }
  return null
}

/** 번역 jsonb에 사용자 locale 키가 있는지. */
export function hasLocale(
  translations: Translations | null | undefined,
  locale: Locale,
): boolean {
  return !!translations && typeof translations[locale] === 'string' && !!translations[locale]
}
