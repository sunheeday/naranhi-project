export const locales = ['ko', 'en', 'zh', 'vi', 'ru', 'ar', 'fr', 'id', 'th'] as const
export type Locale = (typeof locales)[number]
export const defaultLocale: Locale = 'ko'

export const localeNames: Record<Locale, string> = {
  ko: '한국어',
  en: 'English',
  zh: '中文 (简体)',
  vi: 'Tiếng Việt',
  ru: 'Русский',
  ar: 'العربية',
  fr: 'Français',
  id: 'Bahasa Indonesia',
  th: 'ไทย',
}

export const localeFlags: Record<Locale, string> = {
  ko: '🇰🇷',
  en: '🇬🇧',
  zh: '🇨🇳',
  vi: '🇻🇳',
  ru: '🇷🇺',
  ar: '🇸🇦',
  fr: '🇫🇷',
  id: '🇮🇩',
  th: '🇹🇭',
}

/** RTL 사용 언어. layout.tsx에서 <html dir>에 사용. */
export const RTL_LOCALES: ReadonlySet<Locale> = new Set(['ar'])

export function isValidLocale(value: unknown): value is Locale {
  return locales.includes(value as Locale)
}

export function isRtl(locale: Locale): boolean {
  return RTL_LOCALES.has(locale)
}
