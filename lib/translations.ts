/**
 * 다국어 번역 jsonb 헬퍼.
 *
 * 모든 번역 가능한 콘텐츠 (notices.summary_translations, notice_cards.content)는
 * { [locale]: string } 형태의 jsonb로 저장된다. 사용자 locale에 해당 키가 있으면
 * 그 값을, 없으면 ko로 fallback. ko도 없으면 첫 번째 키.
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
