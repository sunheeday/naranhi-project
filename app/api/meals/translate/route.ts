import { NextResponse, type NextRequest } from 'next/server'
import { isValidLocale } from '@/lib/i18n'
import { translateMealCollectionsForLocale, type Meal } from '@/lib/neis'

interface RequestBody {
  locale?: unknown
  collections?: unknown
}

function isMealDish(value: unknown): value is Meal['dishes'][number] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const dish = value as Record<string, unknown>
  return (
    typeof dish.name === 'string'
    && Array.isArray(dish.allergens)
    && dish.allergens.every(code => typeof code === 'number')
  )
}

function isMeal(value: unknown): value is Meal {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const meal = value as Record<string, unknown>
  return (
    typeof meal.mealType === 'number'
    && typeof meal.mealTypeName === 'string'
    && Array.isArray(meal.dishes)
    && meal.dishes.every(isMealDish)
  )
}

/** 요청 크기 상한. 이 주소는 임의 문자열을 AI 번역으로 넘기므로 «개수·길이» 를 막는다.
 *  실제 사용은 5일 x 식사 1~3개 x 메뉴 십여 개(메뉴명 30자 안팎)라 아래 값은 그보다 훨씬 넉넉하다. */
const MAX_DAYS = 7
const MAX_MEALS_PER_DAY = 5
const MAX_DISHES_PER_MEAL = 40
const MAX_DISH_NAME_LENGTH = 200

function withinLimits(collections: Meal[][]): boolean {
  return (
    collections.length <= MAX_DAYS
    && collections.every(meals =>
      meals.length <= MAX_MEALS_PER_DAY
      && meals.every(meal =>
        meal.dishes.length <= MAX_DISHES_PER_MEAL
        && meal.dishes.every(dish => dish.name.length <= MAX_DISH_NAME_LENGTH),
      ),
    )
  )
}

function isMealCollections(value: unknown): value is Meal[][] {
  return (
    Array.isArray(value)
    && value.every(meals => Array.isArray(meals) && meals.every(isMeal))
    && withinLimits(value as Meal[][])
  )
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as RequestBody | null
  if (!body || !isValidLocale(body.locale)) {
    return NextResponse.json({ ok: false, error: 'invalid_locale' }, { status: 400 })
  }
  if (!isMealCollections(body.collections)) {
    return NextResponse.json({ ok: false, error: 'invalid_collections' }, { status: 400 })
  }

  try {
    const translated = await translateMealCollectionsForLocale(body.collections, body.locale)
    return NextResponse.json({ ok: true, collections: translated })
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : 'meal_translation_failed',
      },
      { status: 500 },
    )
  }
}
