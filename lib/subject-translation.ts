/**
 * 시간표 과목명 번역 오케스트레이션 (Tier 1 사전 → Tier 2 즉석 번역 + 영구 캐시).
 *
 * 흐름:
 *   1) resolveStaticSubject  — 정적 사전 적중 시 즉시 반환 (무비용)
 *   2) in-memory 캐시        — 동일 프로세스 반복 조회 절감
 *   3) subject_translations  — DB 영구 캐시 SELECT (앱 전체 공유)
 *   4) 백엔드 Gemini 배치 호출 — 위에서 못 찾은 과목만 1회 호출 후 캐시 UPSERT
 *   5) 그래도 못 찾으면 한글 원문 유지 (graceful fallback)
 *
 * 급식 번역(lib/neis.ts translateMealCollectionsForLocale + /notices/translate-text
 * translation_kind='meal_labels')을 모방하되, 콜드스타트마다 재번역되는 인메모리-only
 * 캐시 대신 DB 영구 캐시를 추가해 Gemini 429 쿼터를 보호한다.
 */

import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '@/types/database'
import type { Locale } from '@/lib/i18n'
import type { TimetableDayEntry } from '@/app/(app)/calendar/TimetableWeekView'
import {
  applySubjectSuffix,
  resolveStaticSubject,
  splitSubjectSuffix,
} from '@/lib/subject-dictionary'

/** base(접미사 제거) 단위 인메모리 캐시. 키: `${locale}:${base}` → 번역된 base. */
const subjectMemCache = new Map<string, string>()

const BACKEND_TIMEOUT_MS = 8000

function subjectToken(index: number): string {
  return `S${String(index + 1).padStart(3, '0')}`
}

/**
 * 시간표 하루치 배열의 과목명을 locale로 번역한다.
 * 표시 컴포넌트는 변경 없이 번역된 `subject`를 그대로 받는다.
 */
export async function translateTimetableDays(
  days: TimetableDayEntry[],
  locale: Locale,
  client?: SupabaseClient<Database>,
): Promise<TimetableDayEntry[]> {
  if (locale === 'ko') return days
  const subjects = days.flatMap(day => day.periods.map(period => period.subject))
  const map = await buildSubjectTranslationMap(subjects, locale, client)
  if (map.size === 0) return days
  return days.map(day => ({
    ...day,
    periods: day.periods.map(period => ({
      ...period,
      subject: map.get(period.subject.trim()) ?? period.subject,
    })),
  }))
}

/**
 * 원문 과목 문자열 → 번역 문자열 맵을 만든다.
 * 해결하지 못한 과목은 맵에 넣지 않는다(호출부에서 원문 폴백).
 */
export async function buildSubjectTranslationMap(
  subjects: string[],
  locale: Locale,
  client?: SupabaseClient<Database>,
): Promise<Map<string, string>> {
  const result = new Map<string, string>()
  if (locale === 'ko') return result

  const uniqueRaw = Array.from(
    new Set(subjects.map(text => text.trim()).filter(Boolean)),
  )

  // 정적 사전·인메모리 캐시로 못 해결한 항목을 base별로 모은다.
  const pendingByBase = new Map<string, Array<{ suffix: string; raw: string }>>()

  for (const raw of uniqueRaw) {
    const fromDict = resolveStaticSubject(raw, locale)
    if (fromDict) {
      result.set(raw, fromDict)
      continue
    }
    const { base, suffix } = splitSubjectSuffix(raw)
    if (!base) continue
    const memHit = subjectMemCache.get(`${locale}:${base}`)
    if (memHit) {
      result.set(raw, applySubjectSuffix(memHit, suffix))
      continue
    }
    const list = pendingByBase.get(base) ?? []
    list.push({ suffix, raw })
    pendingByBase.set(base, list)
  }

  if (pendingByBase.size === 0) return result

  const applyBaseTranslation = (base: string, translatedBase: string) => {
    subjectMemCache.set(`${locale}:${base}`, translatedBase)
    for (const { suffix, raw } of pendingByBase.get(base) ?? []) {
      result.set(raw, applySubjectSuffix(translatedBase, suffix))
    }
  }

  let remainingBases = Array.from(pendingByBase.keys())

  // DB 영구 캐시 조회.
  if (client) {
    const { data, error } = await client
      .from('subject_translations')
      .select('ko_subject, translated')
      .eq('locale', locale)
      .in('ko_subject', remainingBases)
    if (error) {
      console.error('[subject-translation] cache select failed:', error.message)
    } else if (data) {
      const resolved = new Set<string>()
      for (const row of data) {
        applyBaseTranslation(row.ko_subject, row.translated)
        resolved.add(row.ko_subject)
      }
      remainingBases = remainingBases.filter(base => !resolved.has(base))
    }
  }

  if (remainingBases.length === 0) return result

  // 백엔드 즉석 번역(배치 1회) → 영구 캐시 UPSERT.
  const translatedBases = await translateSubjectBasesViaBackend(remainingBases, locale)
  const upsertRows: Array<{ ko_subject: string; locale: string; translated: string }> = []
  for (const base of remainingBases) {
    const translated = translatedBases[base]
    if (!translated) continue // 미해결 → result 미포함 → 원문 폴백
    applyBaseTranslation(base, translated)
    upsertRows.push({ ko_subject: base, locale, translated })
  }

  if (client && upsertRows.length > 0) {
    await client
      .from('subject_translations')
      .upsert(upsertRows, { onConflict: 'ko_subject,locale' })
      .then(({ error }) => {
        if (error) console.error('[subject-translation] cache upsert failed:', error.message)
      })
  }

  return result
}

/** 미등록 과목 base들을 백엔드 Gemini로 배치 번역. base → 번역 맵 반환(실패 시 빈 맵). */
async function translateSubjectBasesViaBackend(
  bases: string[],
  locale: Locale,
): Promise<Record<string, string>> {
  if (bases.length === 0) return {}
  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')
  if (!apiBase) return {}

  const sourceText = [
    '# 시간표 과목 번역 항목',
    ...bases.map((base, index) => `[[${subjectToken(index)}]] ${base}`),
  ].join('\n')

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS)
  try {
    const response = await fetch(`${apiBase}/notices/translate-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_text: sourceText,
        target_language: locale,
        translation_kind: 'subject_labels',
      }),
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!response.ok) return {}

    const body = (await response.json()) as {
      translations?: Record<string, string> | null
      translation?: string | null
      pipeline_result?: { final_translation?: string | null } | null
    }

    if (body.translations && typeof body.translations === 'object') {
      const direct: Record<string, string> = {}
      bases.forEach((base, index) => {
        const translated = body.translations?.[subjectToken(index)]
        if (typeof translated === 'string' && translated.trim()) {
          direct[base] = translated.trim()
        }
      })
      if (Object.keys(direct).length > 0) return direct
    }

    const text = body.pipeline_result?.final_translation ?? body.translation ?? ''
    return parseSubjectMarkerOutput(text, bases)
  } catch (e) {
    console.error('[subject-translation] backend call failed:', e instanceof Error ? e.message : e)
    return {}
  } finally {
    clearTimeout(timer)
  }
}

/** `[[S001]] 번역` 마커 텍스트를 base → 번역 맵으로 파싱(translations 맵이 없을 때 폴백). */
function parseSubjectMarkerOutput(
  translatedText: string,
  bases: string[],
): Record<string, string> {
  const byToken = new Map<string, string>()
  for (const rawLine of translatedText.split('\n')) {
    const line = rawLine.trim()
    const match = line.match(/^(?:[-*]\s*)?\[\[(S\d{3})\]\]\s*[:\-–]?\s*(.+?)\s*$/)
    if (!match) continue
    byToken.set(match[1], match[2].trim())
  }
  const result: Record<string, string> = {}
  bases.forEach((base, index) => {
    const translated = byToken.get(subjectToken(index))
    if (translated) result[base] = translated
  })
  return result
}
