import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import {
  ensureDemoSchoolSeed,
  getSeededDemoMealsForRange,
  isDemoSchoolSelection,
} from '@/lib/demo-school'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import { getLatestChildForUser } from '@/lib/server-cache'
import { ensureTestBypassChild, isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'
import { annotateMealsWithDietaryWarnings, parseDietaryRestrictions, type DietaryRestrictionId } from '@/lib/dietary-restrictions'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import { getCachedOrFetchMealsForRange, type Meal } from '@/lib/neis'
import BrandHeader from '@/components/brand/BrandHeader'
import MealWeekView, { type DayEntry } from './MealWeekView'

interface Props {
  searchParams: Promise<{ week?: string }>
}

function parseJsonCookie(value: string | undefined): unknown {
  if (!value) return []
  try {
    return JSON.parse(value) as unknown
  } catch {
    return []
  }
}

/**
 * ISO 날짜 문자열을 시간대 영향 없이 다루기 위한 헬퍼.
 * KST 자정 + UTC 메서드를 섞으면 1일 밀리는 버그가 생기므로,
 * 모든 계산을 UTC 자정 기준으로 통일한다 (날짜만 다루므로 안전).
 */
function isoParts(iso: string): { y: number; m: number; d: number; weekday: number; ms: number } {
  const [y, m, d] = iso.split('-').map(Number)
  const ms = Date.UTC(y, m - 1, d)
  return { y, m, d, weekday: new Date(ms).getUTCDay(), ms }
}

function msToIso(ms: number): string {
  const dt = new Date(ms)
  const yy = dt.getUTCFullYear()
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(dt.getUTCDate()).padStart(2, '0')
  return `${yy}-${mm}-${dd}`
}

function startOfWeekMonday(iso: string): string {
  const { weekday, ms } = isoParts(iso)
  const diff = weekday === 0 ? -6 : 1 - weekday
  return msToIso(ms + diff * 86400000)
}

function addDaysIso(iso: string, days: number): string {
  const { ms } = isoParts(iso)
  return msToIso(ms + days * 86400000)
}

/** Asia/Seoul 기준 오늘 ISO. 서버 시간대에 무관. */
function todayKstIso(): string {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return fmt.format(new Date())
}

export default async function MealsPage({ searchParams }: Props) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const testDietaryRestrictions = parseDietaryRestrictions(parseJsonCookie(cookieStore.get('test_dietary_restrictions')?.value))
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  const params = await searchParams
  const todayIso = todayKstIso()
  const baseIso = params.week && /^\d{4}-\d{2}-\d{2}$/.test(params.week) ? params.week : todayIso

  const monday = startOfWeekMonday(baseIso)
  const friday = addDaysIso(monday, 4)  // 월~금 (학교 급식 기준)

  let dayEntries: DayEntry[] = []
  let unsupported = false
  let errorMessage: string | null = null
  let childLabel = ''
  let dietaryRestrictions: DietaryRestrictionId[] = []

  if (await isUiPreviewEnabled()) {
    dayEntries = await previewMealEntries(monday, locale)
    childLabel = '나란히초등학교 3-2'
  } else {
    const testEntryBypass = isTestEntryBypassEnabled()
    const supabase = testEntryBypass
      ? createSupabaseServiceClient()
      : await createSupabaseServerClient()
    const { data: { user } } = testEntryBypass
      ? { data: { user: null } }
      : await supabase.auth.getUser()
    if (!user && !testEntryBypass) redirect('/login')

    const child = testEntryBypass
      ? await ensureTestBypassChild()
      : await getLatestChildForUser(user!.id)

    if (!child) redirect('/onboarding')
    childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`
    dietaryRestrictions = testEntryBypass
      ? testDietaryRestrictions
      : child.dietary_restrictions

    const isDemoSchool = isDemoSchoolSelection({
      schoolName: child.school_name,
      neisOfficeCode: child.neis_office_code,
      neisSchoolCode: child.neis_school_code,
    })
    if (isDemoSchool) {
      const serviceClient = await createSupabaseServiceClient()
      try {
        if (child.school_id && !testEntryBypass) {
          await ensureDemoSchoolSeed(serviceClient, child.school_id)
        }
        const map = await getSeededDemoMealsForRange(serviceClient, monday, friday)
        const days: DayEntry[] = []
        let hasAnyMeals = false
        for (let i = 0; i < 5; i++) {
          const iso = addDaysIso(monday, i)
          const rows = map.get(iso) ?? []
          const meals = rows.map(row => ({
            mealType: row.meal_type,
            mealTypeName: row.meal_type_name,
            dishes: Array.isArray(row.dishes) ? (row.dishes as unknown as Meal['dishes']) : [],
            calories: row.calories,
            nutrients: Array.isArray(row.nutrients) ? (row.nutrients as Meal['nutrients']) : null,
            origins: Array.isArray(row.origins) ? (row.origins as Meal['origins']) : null,
          }))
          if (meals.length > 0) hasAnyMeals = true
          days.push({ isoDate: iso, meals })
        }
        dayEntries = hasAnyMeals ? days : await previewMealEntries(monday, locale)
      } catch (e) {
        console.error('[meals] demo fetch failed:', e instanceof Error ? e.message : e)
        dayEntries = await previewMealEntries(monday, locale)
      }
    } else if (!child.neis_office_code || !child.neis_school_code) {
      unsupported = true
    } else {
      try {
        const serviceClient = await createSupabaseServiceClient()
        const map = await getCachedOrFetchMealsForRange(
          serviceClient,
          child.neis_office_code,
          child.neis_school_code,
          monday,
          friday,
        )
        const rawMealsByDay: Meal[][] = []
        for (let i = 0; i < 5; i++) {
          const iso = addDaysIso(monday, i)
          rawMealsByDay.push(map.get(iso) ?? [])
        }
        const days: DayEntry[] = []
        for (let i = 0; i < 5; i++) {
          const iso = addDaysIso(monday, i)
          days.push({
            isoDate: iso,
            meals: rawMealsByDay[i] ?? [],
          })
        }
        dayEntries = days
      } catch (e) {
        console.error('[meals] fetch failed:', e instanceof Error ? e.message : e)
        errorMessage = messages.meals?.error ?? '급식 정보를 불러오지 못했어요.'
        const days: DayEntry[] = []
        for (let i = 0; i < 5; i++) {
          days.push({ isoDate: addDaysIso(monday, i), meals: [] as Meal[] })
        }
        dayEntries = days
      }
    }

    if (dietaryRestrictions.length > 0) {
      dayEntries = dayEntries.map(day => ({
        ...day,
        meals: annotateMealsWithDietaryWarnings(day.meals, dietaryRestrictions, locale),
      }))
    }
  }

  const m = messages.meals ?? {}
  const labels = {
    weekday: messages.calendar.weekdays as string[],
    prev_week: m.prev_week ?? '이전 주',
    next_week: m.next_week ?? '다음 주',
    this_week: m.this_week ?? '이번 주',
    no_meal: m.no_meal ?? '급식 없음',
    breakfast: messages.home.meal_breakfast ?? '조식',
    lunch: messages.home.meal_lunch ?? '중식',
    dinner: messages.home.meal_dinner ?? '석식',
    allergy_prefix: messages.home.meal_allergy_prefix ?? '⚠ 알레르기:',
    range: m.range ?? '{startMonth}/{startDay} – {endMonth}/{endDay}',
    today_label: m.today ?? '오늘',
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <BrandHeader title={m.title ?? '급식'} subtitle={childLabel || undefined} character="readingYellow" />

      {unsupported && (
        <div role="alert" className="mx-6 mt-4 rounded-card border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {m.unsupported ?? '학교 코드가 등록되지 않았어요. 설정에서 학교를 다시 선택해 주세요.'}
        </div>
      )}

      {errorMessage && (
        <div role="alert" className="mx-6 mt-4 rounded-card border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {errorMessage}
        </div>
      )}

      {!unsupported && (
        <MealWeekView
          key={`${monday}:${locale}`}
          weekStartIso={monday}
          days={dayEntries}
          locale={locale}
          labels={{
            ...labels,
            translation_pending: m.translation_pending ?? '급식 번역 중...',
            translation_pending_body: m.translation_pending_body ?? '한국어 급식을 먼저 보여드리고 있어요.',
            translation_error: m.error ?? messages.common.error_generic,
            loading: messages.common.loading,
          }}
        />
      )}
    </main>
  )
}

async function previewMealEntries(monday: string, locale: Locale): Promise<DayEntry[]> {
  const menus: Meal[][] = [
    [{
      mealType: 2,
      mealTypeName: '중식',
      dishes: [
        { name: '현미밥', allergens: [] },
        { name: '미역국', allergens: [5] },
        { name: '닭갈비', allergens: [5, 15] },
        { name: '배추김치', allergens: [] },
      ],
      calories: '672 Kcal',
      nutrients: null,
      origins: null,
    }],
    [{
      mealType: 2,
      mealTypeName: '중식',
      dishes: [
        { name: '카레라이스', allergens: [2, 6] },
        { name: '오이무침', allergens: [] },
        { name: '요구르트', allergens: [2] },
      ],
      calories: '701 Kcal',
      nutrients: null,
      origins: null,
    }],
    [],
    [{
      mealType: 2,
      mealTypeName: '중식',
      dishes: [
        { name: '보리밥', allergens: [] },
        { name: '된장찌개', allergens: [5, 6] },
        { name: '생선구이', allergens: [7] },
      ],
      calories: '645 Kcal',
      nutrients: null,
      origins: null,
    }],
    [{
      mealType: 2,
      mealTypeName: '중식',
      dishes: [
        { name: '김치볶음밥', allergens: [5, 10] },
        { name: '계란국', allergens: [1] },
        { name: '사과', allergens: [] },
      ],
      calories: '628 Kcal',
      nutrients: null,
      origins: null,
    }],
  ]

  return menus.map((meals, index) => ({
    isoDate: addDaysIso(monday, index),
    meals,
  }))
}
