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

/**
 * 월/일 짧은 날짜를 로케일의 주간 범위 템플릿과 같은 순서로 표기한다.
 * 템플릿에서 {startDay}가 {startMonth}보다 앞이면 일/월(예: 베트남어 8/6),
 * 그 외에는 월/일(예: 한국어 6/8). 같은 화면에서 표기가 섞이지 않게 한다.
 */
export function formatMonthDay(month: number, day: number, rangeTemplate: string): string {
  const dayIdx = rangeTemplate.indexOf('{startDay}')
  const monthIdx = rangeTemplate.indexOf('{startMonth}')
  const dayFirst = dayIdx !== -1 && monthIdx !== -1 && dayIdx < monthIdx
  return dayFirst ? `${day}/${month}` : `${month}/${day}`
}
