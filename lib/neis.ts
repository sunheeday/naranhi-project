/**
 * NEIS Open API 클라이언트.
 *
 * - 학교 정보(`schoolInfo`) + 급식 정보(`mealServiceDietInfo`) 조회
 * - 급식 데이터는 meals 테이블에 캐싱 (학교 단위 공유)
 *
 * 필요 환경변수:
 *   NEIS_API_KEY (https://open.neis.go.kr 발급)
 */

import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database, Json } from '@/types/database'
import type { Locale } from '@/lib/i18n'

const NEIS_BASE = 'https://open.neis.go.kr/hub'
const PAGE_SIZE = 100
const mealTranslationCache = new Map<string, string>()
const mealTranslationBatchCache = new Map<string, Record<string, string>>()

export interface SchoolSearchResult {
  officeCode: string   // ATPT_OFCDC_SC_CODE (시도교육청 코드)
  schoolCode: string   // SD_SCHUL_CODE (행정표준코드)
  name: string         // SCHUL_NM
  level: string        // SCHUL_KND_SC_NM (초등학교/중학교/고등학교)
  address: string      // ORG_RDNMA
  homepageUrl: string  // HMPG_ADRES
}

export interface MealDish {
  name: string
  allergens: number[]  // 1~19 알레르기 코드
  allergenLabels?: string[]
}

export interface Meal {
  mealType: number       // 1=조식, 2=중식, 3=석식
  mealTypeName: string
  dishes: MealDish[]
  calories: string | null
  nutrients: Array<{ name: string; amount: string }> | null
  origins: Array<{ ingredient: string; country: string }> | null
}

export interface TimetablePeriod {
  date: string            // YYYY-MM-DD
  period: number
  subject: string
  grade: number | null
  className: string | null
  classroom: string | null
}

export class UnsupportedTimetableError extends Error {
  constructor(message = '지원하지 않는 학교 종류입니다.') {
    super(message)
    this.name = 'UnsupportedTimetableError'
  }
}

export const ALLERGEN_NAMES: Record<number, string> = {
  1: '난류', 2: '우유', 3: '메밀', 4: '땅콩', 5: '대두',
  6: '밀', 7: '고등어', 8: '게', 9: '새우', 10: '돼지고기',
  11: '복숭아', 12: '토마토', 13: '아황산류', 14: '호두',
  15: '닭고기', 16: '쇠고기', 17: '오징어', 18: '조개류', 19: '잣',
}

function getApiKey(): string {
  const key = process.env.NEIS_API_KEY
  if (!key) throw new Error('NEIS_API_KEY 환경변수 누락')
  return key
}

async function neisFetch<T>(path: string, params: Record<string, string>): Promise<T> {
  const url = new URL(`${NEIS_BASE}/${path}`)
  url.searchParams.set('KEY', getApiKey())
  url.searchParams.set('Type', 'json')
  url.searchParams.set('pIndex', '1')
  url.searchParams.set('pSize', String(PAGE_SIZE))
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v)

  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) throw new Error(`NEIS ${path} ${res.status}`)
  return (await res.json()) as T
}

interface NeisListEnvelope<R> {
  [key: string]: Array<
    { head: Array<{ list_total_count?: number; RESULT?: { CODE: string; MESSAGE: string } }> } | { row: R[] }
  > | undefined
}

function extractRows<R>(envelope: NeisListEnvelope<R>, key: string): R[] {
  const arr = envelope[key]
  if (!Array.isArray(arr)) return []
  for (const block of arr) {
    if (block && 'row' in block && Array.isArray(block.row)) return block.row
  }
  return []
}

// ─── 학교 검색 ────────────────────────────────────────────

interface SchoolInfoRow {
  ATPT_OFCDC_SC_CODE: string
  SD_SCHUL_CODE: string
  SCHUL_NM: string
  SCHUL_KND_SC_NM: string
  ORG_RDNMA: string | null
  HMPG_ADRES?: string | null
}

export async function searchSchools(query: string): Promise<SchoolSearchResult[]> {
  const trimmed = query.trim()
  if (trimmed.length < 2) return []

  const data = await neisFetch<NeisListEnvelope<SchoolInfoRow>>('schoolInfo', {
    SCHUL_NM: trimmed,
  })
  const rows = extractRows(data, 'schoolInfo')

  return rows.map(r => ({
    officeCode: r.ATPT_OFCDC_SC_CODE,
    schoolCode: r.SD_SCHUL_CODE,
    name: r.SCHUL_NM,
    level: r.SCHUL_KND_SC_NM,
    address: r.ORG_RDNMA ?? '',
    homepageUrl: normalizeHomepageUrl(r.HMPG_ADRES),
  }))
}

function normalizeHomepageUrl(value: string | null | undefined): string {
  const trimmed = (value ?? '').trim()
  if (!trimmed) return ''
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return `https://${trimmed}`
}

// ─── 시간표 ───────────────────────────────────────────────

interface TimetableRow {
  ALL_TI_YMD: string
  GRADE?: string | null
  CLASS_NM?: string | null
  PERIO: string
  ITRT_CNTNT: string | null
  CLRM_NM?: string | null
}

type TimetableEndpoint = 'elsTimetable' | 'misTimetable' | 'hisTimetable' | 'spsTimetable'

function resolveTimetableEndpoint(levelOrName: string | null | undefined): TimetableEndpoint | null {
  const value = levelOrName ?? ''
  if (value.includes('초등') || value.includes('초등학교')) return 'elsTimetable'
  if (value.includes('중학') || value.includes('중학교')) return 'misTimetable'
  if (value.includes('고등') || value.includes('고등학교')) return 'hisTimetable'
  if (value.includes('특수')) return 'spsTimetable'
  return null
}

async function fetchSchoolLevelFromNeis(
  officeCode: string,
  schoolCode: string,
): Promise<string | null> {
  const data = await neisFetch<NeisListEnvelope<SchoolInfoRow>>('schoolInfo', {
    ATPT_OFCDC_SC_CODE: officeCode,
    SD_SCHUL_CODE: schoolCode,
  })
  return extractRows(data, 'schoolInfo')[0]?.SCHUL_KND_SC_NM ?? null
}

function isoFromYmd(yyyymmdd: string): string {
  return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`
}

function stripHtml(value: string): string {
  return value.replace(/<br\s*\/?>/g, ' ').replace(/<[^>]+>/g, '').trim()
}

/** 날짜 범위로 NEIS 시간표 조회. YYYYMMDD ~ YYYYMMDD (양 끝 포함). */
export async function fetchTimetableRangeFromNeis(
  officeCode: string,
  schoolCode: string,
  schoolName: string,
  grade: number,
  classNo: number,
  fromYmd: string,
  toYmd: string,
): Promise<TimetablePeriod[]> {
  let endpoint = resolveTimetableEndpoint(schoolName)
  if (!endpoint) {
    endpoint = resolveTimetableEndpoint(await fetchSchoolLevelFromNeis(officeCode, schoolCode))
  }
  if (!endpoint) throw new UnsupportedTimetableError()

  try {
    const data = await neisFetch<NeisListEnvelope<TimetableRow>>(endpoint, {
      ATPT_OFCDC_SC_CODE: officeCode,
      SD_SCHUL_CODE: schoolCode,
      GRADE: String(grade),
      CLASS_NM: String(classNo),
      TI_FROM_YMD: fromYmd,
      TI_TO_YMD: toYmd,
    })
    const rows = extractRows(data, endpoint)
    return rows
      .map(r => ({
        date: isoFromYmd(r.ALL_TI_YMD),
        period: parseInt(r.PERIO, 10),
        subject: stripHtml(r.ITRT_CNTNT ?? ''),
        grade: r.GRADE ? parseInt(r.GRADE, 10) : null,
        className: r.CLASS_NM ?? null,
        classroom: r.CLRM_NM ?? null,
      }))
      .filter(row => row.subject && Number.isFinite(row.period))
      .sort((a, b) => a.date.localeCompare(b.date) || a.period - b.period)
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    if (/INFO-200|해당 자료가 없습니다/.test(msg)) return []
    throw e
  }
}

// ─── 급식 ────────────────────────────────────────────────

interface MealRow {
  MMEAL_SC_CODE: string  // "1"|"2"|"3"
  MMEAL_SC_NM: string    // "조식"|"중식"|"석식"
  DDISH_NM: string
  ORPLC_INFO: string | null
  CAL_INFO: string | null
  NTR_INFO: string | null
}

function parseDishes(ddish: string): MealDish[] {
  // "쌀밥<br/>김치찌개*5.6.7<br/>제육볶음*5.10" → [{name, allergens:[]}]
  return ddish
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const m = line.match(/^(.+?)\s*\(?([\d.]+)\)?\s*$/)
      if (m && m[2].includes('.')) {
        return {
          name: m[1].trim(),
          allergens: m[2].split('.').map(s => parseInt(s, 10)).filter(n => !Number.isNaN(n)),
        }
      }
      // 형식이 "이름*5.6.7" 인 경우
      const star = line.split('*')
      if (star.length === 2) {
        return {
          name: star[0].trim(),
          allergens: star[1].split('.').map(s => parseInt(s, 10)).filter(n => !Number.isNaN(n)),
        }
      }
      return { name: line, allergens: [] }
    })
}

function parseBrLines(s: string | null): Array<{ name: string; amount: string }> | null {
  if (!s) return null
  return s
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const m = line.match(/^(.+?)\s*[:\-]\s*(.+)$/)
      if (m) return { name: m[1].trim(), amount: m[2].trim() }
      return { name: line, amount: '' }
    })
}

function parseOrigins(s: string | null): Array<{ ingredient: string; country: string }> | null {
  if (!s) return null
  return s
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const m = line.match(/^(.+?)\s*[:\-]\s*(.+)$/)
      if (m) return { ingredient: m[1].trim(), country: m[2].trim() }
      return { ingredient: line, country: '' }
    })
}

/** NEIS API에서 직접 조회 (캐시 미사용). YYYYMMDD. */
export async function fetchMealsFromNeis(
  officeCode: string,
  schoolCode: string,
  yyyymmdd: string,
): Promise<Meal[]> {
  try {
    const data = await neisFetch<NeisListEnvelope<MealRow>>('mealServiceDietInfo', {
      ATPT_OFCDC_SC_CODE: officeCode,
      SD_SCHUL_CODE: schoolCode,
      MLSV_YMD: yyyymmdd,
    })
    const rows = extractRows(data, 'mealServiceDietInfo')
    return rows.map(r => ({
      mealType: parseInt(r.MMEAL_SC_CODE, 10),
      mealTypeName: r.MMEAL_SC_NM,
      dishes: parseDishes(r.DDISH_NM ?? ''),
      calories: r.CAL_INFO,
      nutrients: parseBrLines(r.NTR_INFO),
      origins: parseOrigins(r.ORPLC_INFO),
    }))
  } catch (e) {
    // NEIS는 데이터 없으면 INFO-200 에러를 RESULT에 담아 보냄. 정상으로 처리.
    const msg = e instanceof Error ? e.message : String(e)
    if (/INFO-200|해당 자료가 없습니다/.test(msg)) return []
    throw e
  }
}

interface MealRowWithDate extends MealRow {
  MLSV_YMD: string  // YYYYMMDD
}

/** 날짜 범위로 NEIS 조회 (캐시 미사용). YYYYMMDD ~ YYYYMMDD (양 끝 포함). */
export async function fetchMealsRangeFromNeis(
  officeCode: string,
  schoolCode: string,
  fromYmd: string,
  toYmd: string,
): Promise<Array<Meal & { date: string }>> {
  try {
    const data = await neisFetch<NeisListEnvelope<MealRowWithDate>>('mealServiceDietInfo', {
      ATPT_OFCDC_SC_CODE: officeCode,
      SD_SCHUL_CODE: schoolCode,
      MLSV_FROM_YMD: fromYmd,
      MLSV_TO_YMD: toYmd,
    })
    const rows = extractRows(data, 'mealServiceDietInfo')
    return rows.map(r => ({
      mealType: parseInt(r.MMEAL_SC_CODE, 10),
      mealTypeName: r.MMEAL_SC_NM,
      dishes: parseDishes(r.DDISH_NM ?? ''),
      calories: r.CAL_INFO,
      nutrients: parseBrLines(r.NTR_INFO),
      origins: parseOrigins(r.ORPLC_INFO),
      date: `${r.MLSV_YMD.slice(0, 4)}-${r.MLSV_YMD.slice(4, 6)}-${r.MLSV_YMD.slice(6, 8)}`,
    }))
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    if (/INFO-200|해당 자료가 없습니다/.test(msg)) return []
    throw e
  }
}

/** 캐시 우선 조회. 캐시 미스 시 NEIS 호출 후 저장. */
export async function getCachedOrFetchMeals(
  client: SupabaseClient<Database>,
  officeCode: string,
  schoolCode: string,
  isoDate: string,    // YYYY-MM-DD
): Promise<Meal[]> {
  const { data: cached } = await client
    .from('meals')
    .select('meal_type, meal_type_name, dishes, calories, nutrients, origins')
    .eq('office_code', officeCode)
    .eq('school_code', schoolCode)
    .eq('meal_date', isoDate)
    .order('meal_type', { ascending: true })

  if (cached && cached.length > 0) {
    return cached.map(r => ({
      mealType: r.meal_type,
      mealTypeName: r.meal_type_name,
      dishes: r.dishes as unknown as MealDish[],
      calories: r.calories,
      nutrients: r.nutrients as unknown as Meal['nutrients'],
      origins: r.origins as unknown as Meal['origins'],
    }))
  }

  const yyyymmdd = isoDate.replace(/-/g, '')
  const meals = await fetchMealsFromNeis(officeCode, schoolCode, yyyymmdd)
  if (meals.length === 0) return []

  // 캐시 저장 (실패해도 결과는 반환)
  await client
    .from('meals')
    .upsert(
      meals.map(m => ({
        office_code: officeCode,
        school_code: schoolCode,
        meal_date: isoDate,
        meal_type: m.mealType,
        meal_type_name: m.mealTypeName,
        dishes: m.dishes as unknown as Json,
        calories: m.calories,
        nutrients: (m.nutrients ?? null) as unknown as Json,
        origins: (m.origins ?? null) as unknown as Json,
      })),
      { onConflict: 'office_code,school_code,meal_date,meal_type' },
    )
    .then(({ error }) => {
      if (error) console.error('[neis] meals upsert failed:', error.message)
    })

  return meals
}

/**
 * 날짜 범위(양 끝 포함) 캐시 우선 조회.
 * - DB에 있는 날짜는 그대로 사용
 * - 없는 날짜만 NEIS 한 번에 호출 후 upsert
 * 반환은 날짜 → 메뉴 배열 맵.
 */
export async function getCachedOrFetchMealsForRange(
  client: SupabaseClient<Database>,
  officeCode: string,
  schoolCode: string,
  fromIso: string,    // YYYY-MM-DD
  toIso: string,      // YYYY-MM-DD (양 끝 포함)
): Promise<Map<string, Meal[]>> {
  const result = new Map<string, Meal[]>()

  const { data: cached } = await client
    .from('meals')
    .select('meal_date, meal_type, meal_type_name, dishes, calories, nutrients, origins')
    .eq('office_code', officeCode)
    .eq('school_code', schoolCode)
    .gte('meal_date', fromIso)
    .lte('meal_date', toIso)
    .order('meal_type', { ascending: true })

  for (const r of cached ?? []) {
    const arr = result.get(r.meal_date) ?? []
    arr.push({
      mealType: r.meal_type,
      mealTypeName: r.meal_type_name,
      dishes: r.dishes as unknown as MealDish[],
      calories: r.calories,
      nutrients: r.nutrients as unknown as Meal['nutrients'],
      origins: r.origins as unknown as Meal['origins'],
    })
    result.set(r.meal_date, arr)
  }

  // 모든 날짜 후보 산출
  const allDates: string[] = []
  for (let d = new Date(`${fromIso}T00:00:00+09:00`); d <= new Date(`${toIso}T00:00:00+09:00`); d.setUTCDate(d.getUTCDate() + 1)) {
    allDates.push(d.toISOString().slice(0, 10))
  }
  const missingDates = allDates.filter(d => !result.has(d))
  if (missingDates.length === 0) return result

  // NEIS는 휴일에 빈 응답을 주므로, 캐시 미스 = 데이터 없음일 수 있음.
  // 한 주 단위로 호출하면 유효한 데이터만 모아 옴 → 결과에 없는 날짜는 빈 배열로 둔다.
  const fromYmd = fromIso.replace(/-/g, '')
  const toYmd = toIso.replace(/-/g, '')
  const fetched = await fetchMealsRangeFromNeis(officeCode, schoolCode, fromYmd, toYmd)

  // 캐시에 이미 있던 날짜는 NEIS 결과로 덮어쓰지 않음 (불필요한 upsert 방지)
  const newRows: Array<{
    office_code: string
    school_code: string
    meal_date: string
    meal_type: number
    meal_type_name: string
    dishes: Json
    calories: string | null
    nutrients: Json
    origins: Json
  }> = []

  const fetchedByDate = new Map<string, Meal[]>()
  for (const m of fetched) {
    const arr = fetchedByDate.get(m.date) ?? []
    arr.push({
      mealType: m.mealType,
      mealTypeName: m.mealTypeName,
      dishes: m.dishes,
      calories: m.calories,
      nutrients: m.nutrients,
      origins: m.origins,
    })
    fetchedByDate.set(m.date, arr)
  }

  for (const [date, meals] of fetchedByDate) {
    if (!missingDates.includes(date)) continue
    result.set(date, meals)
    for (const m of meals) {
      newRows.push({
        office_code: officeCode,
        school_code: schoolCode,
        meal_date: date,
        meal_type: m.mealType,
        meal_type_name: m.mealTypeName,
        dishes: m.dishes as unknown as Json,
        calories: m.calories,
        nutrients: (m.nutrients ?? null) as unknown as Json,
        origins: (m.origins ?? null) as unknown as Json,
      })
    }
  }

  if (newRows.length > 0) {
    await client
      .from('meals')
      .upsert(newRows, { onConflict: 'office_code,school_code,meal_date,meal_type' })
      .then(({ error }) => {
        if (error) console.error('[neis] meals upsert (range) failed:', error.message)
      })
  }

  return result
}

export async function translateMealsForLocale(
  meals: Meal[],
  locale: Locale,
): Promise<Meal[]> {
  const [translated] = await translateMealCollectionsForLocale([meals], locale)
  return translated ?? meals
}

export async function translateMealCollectionsForLocale(
  collections: Meal[][],
  locale: Locale,
): Promise<Meal[][]> {
  if (locale === 'ko' || collections.every(meals => meals.length === 0)) return collections

  const uniqueTexts = Array.from(
    new Set(
      collections
        .flatMap(meals => meals)
        .flatMap(meal => [
          meal.mealTypeName,
          ...meal.dishes.map(dish => dish.name),
          ...meal.dishes.flatMap(dish => dish.allergens.map(code => ALLERGEN_NAMES[code] ?? `#${code}`)),
        ])
        .map(text => text.trim())
        .filter(Boolean),
    ),
  )

  const missingTexts = uniqueTexts.filter(text => !mealTranslationCache.has(`${locale}:${text}`))
  if (missingTexts.length > 0) {
    const translated = await translateMealStrings(missingTexts, locale)
    for (const [source, target] of Object.entries(translated)) {
      if (target.trim()) {
        mealTranslationCache.set(`${locale}:${source}`, target.trim())
      }
    }
  }

  return collections.map(meals =>
    meals.map(meal => ({
      ...meal,
      mealTypeName: mealTranslationCache.get(`${locale}:${meal.mealTypeName}`) ?? meal.mealTypeName,
      dishes: meal.dishes.map(dish => ({
        ...dish,
        name: mealTranslationCache.get(`${locale}:${dish.name}`) ?? dish.name,
        allergenLabels: dish.allergens.map(code => {
          const source = ALLERGEN_NAMES[code] ?? `#${code}`
          return mealTranslationCache.get(`${locale}:${source}`) ?? source
        }),
      })),
    })),
  )
}

async function translateMealStrings(
  texts: string[],
  locale: Locale,
): Promise<Record<string, string>> {
  if (texts.length === 0) return {}
  const cacheKey = `${locale}:${texts.join('\u241f')}`
  const cached = mealTranslationBatchCache.get(cacheKey)
  if (cached) return cached
  const translated = await translateMealStringsViaPipeline(texts, locale)
  mealTranslationBatchCache.set(cacheKey, translated)
  return translated
}

async function translateMealStringsViaPipeline(
  texts: string[],
  locale: Locale,
): Promise<Record<string, string>> {
  const apiBase = (
    process.env.FASTAPI_INTERNAL_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || ''
  ).trim().replace(/\/+$/, '')
  if (!apiBase) return {}

  const sourceText = buildMealTranslationSourceText(texts)
  const response = await fetch(`${apiBase}/notices/translate-text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source_text: sourceText,
      target_language: locale,
      translation_kind: 'meal_labels',
    }),
    cache: 'no-store',
  })
  if (!response.ok) return {}

  const body = await response.json() as {
    translations?: Record<string, string> | null
    translation?: string | null
    pipeline_result?: { final_translation?: string | null } | null
  }
  if (body.translations && typeof body.translations === 'object') {
    const direct: Record<string, string> = {}
    texts.forEach((source, index) => {
      const token = `M${String(index + 1).padStart(3, '0')}`
      const translated = body.translations?.[token]
      if (typeof translated === 'string' && translated.trim()) {
        direct[source] = translated.trim()
      }
    })
    if (Object.keys(direct).length > 0) {
      return direct
    }
  }
  const translatedText = body.pipeline_result?.final_translation ?? body.translation ?? ''
  return parseMealTranslationOutput(translatedText, texts)
}

function buildMealTranslationSourceText(texts: string[]): string {
  const lines = texts.map((text, index) => `${mealTranslationToken(index)} ${text}`)
  return ['# 급식 번역 항목', ...lines].join('\n')
}

function parseMealTranslationOutput(
  translatedText: string,
  sourceTexts: string[],
): Record<string, string> {
  const byToken = new Map<string, string>()
  for (const rawLine of translatedText.split('\n')) {
    const line = rawLine.trim()
    const match = line.match(/^(?:[-*]\s*)?\[\[(M\d{3})\]\]\s*[:\-–]?\s*(.+?)\s*$/)
    if (!match) continue
    byToken.set(match[1], match[2].trim())
  }

  const result: Record<string, string> = {}
  sourceTexts.forEach((source, index) => {
    const translated = byToken.get(`M${String(index + 1).padStart(3, '0')}`)
    if (translated) result[source] = translated
  })
  return result
}

function mealTranslationToken(index: number): string {
  return `[[M${String(index + 1).padStart(3, '0')}]]`
}
