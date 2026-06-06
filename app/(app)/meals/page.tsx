import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import { getCachedOrFetchMealsForRange, translateMealCollectionsForLocale, type Meal } from '@/lib/neis'
import { annotateMealCollections, normalizeRestrictions, DIETARY_FLAGS, type DietaryFlag } from '@/lib/dietary'
import BrandHeader from '@/components/brand/BrandHeader'
import MealWeekView, { type DayEntry } from './MealWeekView'

interface Props {
  searchParams: Promise<{ week?: string }>
}

/** dietary flag 라벨 한국어 폴백 (messages에 키 없을 때). */
const DIETARY_FLAG_FALLBACK: Record<DietaryFlag, string> = {
  pork: '돼지고기',
  beef: '쇠고기',
  alcohol: '알코올',
  meat: '육류',
  fish_seafood: '어패류',
  shellfish: '갑각류·조개',
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

  if (await isUiPreviewEnabled()) {
    dayEntries = await previewMealEntries(monday, locale)
    childLabel = '나란히초등학교 3-2'
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) redirect('/login')

    const { data: child } = await supabase
      .from('children')
      .select('id, school_name, grade, class_no, neis_office_code, neis_school_code, dietary_restrictions')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()

    if (!child) redirect('/onboarding')
    childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`

    if (!child.neis_office_code || !child.neis_school_code) {
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
        const restrictions = normalizeRestrictions(child.dietary_restrictions)
        const rawMealsByDay: Meal[][] = []
        for (let i = 0; i < 5; i++) {
          const iso = addDaysIso(monday, i)
          rawMealsByDay.push(map.get(iso) ?? [])
        }
        // 금기 탐지는 번역 전 한국어 메뉴 이름 기준으로 수행한다.
        const annotatedMealsByDay = annotateMealCollections(rawMealsByDay, restrictions)
        const translatedMealsByDay = await translateMealCollectionsForLocale(annotatedMealsByDay, locale)
        const days: DayEntry[] = []
        for (let i = 0; i < 5; i++) {
          const iso = addDaysIso(monday, i)
          days.push({
            isoDate: iso,
            meals: translatedMealsByDay[i] ?? [],
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
  }

  const m = messages.meals ?? {}
  const dietaryMessages = m.dietary ?? {}
  const dietaryLabels = Object.fromEntries(
    DIETARY_FLAGS.map(flag => [flag, dietaryMessages[flag] ?? DIETARY_FLAG_FALLBACK[flag]]),
  ) as Record<DietaryFlag, string>
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
    dietary_prefix: dietaryMessages.prefix ?? '🚫 주의:',
    dietary: dietaryLabels,
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
        <MealWeekView weekStartIso={monday} days={dayEntries} labels={labels} />
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

  // 미리보기에서 기능이 보이도록 대표 금기(채식)로 주석 처리.
  const annotated = annotateMealCollections(menus, ['vegetarian'])
  const translatedMenus = await translateMealCollectionsForLocale(annotated, locale)

  return translatedMenus.map((meals, index) => ({
    isoDate: addDaysIso(monday, index),
    meals,
  }))
}
