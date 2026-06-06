/**
 * 종교/식이 금기 추론 모듈.
 *
 * NEIS 급식 API는 종교 데이터를 제공하지 않는다. 그래서 보호자가 선택한 금기를 기준으로
 * 급식 메뉴를 두 가지 신호로 추론한다:
 *   1) 알레르기 코드 (정확) — 돼지고기(10)·쇠고기(16)·갑각류 등
 *   2) 메뉴 이름 키워드 (보조) — 알코올(맛술/미림)·가공육(햄/소시지) 등 코드로 안 잡히는 항목
 *
 * 키워드 추론은 오탐/누락이 있을 수 있으므로, UI에서는 "주의(확실하지 않음)" 톤으로 표기한다.
 * 키워드 매칭은 반드시 번역 전 한국어 메뉴 이름에 대해 수행해야 한다.
 */

import type { Meal, MealDish } from '@/lib/neis'

/** 보호자가 선택하는 금기 키 (children.dietary_restrictions에 저장). */
export type DietaryRestriction =
  | 'halal'       // 이슬람 / 할랄: 돼지고기 · 알코올
  | 'no_pork'     // 돼지고기 제외
  | 'no_beef'     // 쇠고기 제외 (힌두교 등)
  | 'vegetarian'  // 채식: 육류 · 어패류
  | 'kosher'      // 유대교 / 코셔: 돼지 · 갑각류/조개

export const DIETARY_RESTRICTIONS: DietaryRestriction[] = [
  'halal',
  'no_pork',
  'no_beef',
  'vegetarian',
  'kosher',
]

/** 선택 UI에 쓰는 이모지 (라벨/설명은 messages/*.json의 dietary 섹션). */
export const RESTRICTION_EMOJI: Record<DietaryRestriction, string> = {
  halal: '🌙',
  no_pork: '🐷',
  no_beef: '🐮',
  vegetarian: '🥗',
  kosher: '✡️',
}

export function isDietaryRestriction(value: unknown): value is DietaryRestriction {
  return typeof value === 'string' && (DIETARY_RESTRICTIONS as string[]).includes(value)
}

export function normalizeRestrictions(value: unknown): DietaryRestriction[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<DietaryRestriction>()
  for (const v of value) if (isDietaryRestriction(v)) seen.add(v)
  // DIETARY_RESTRICTIONS 순서로 정렬해 일관된 표시.
  return DIETARY_RESTRICTIONS.filter(r => seen.has(r))
}

/** 메뉴에 표시되는 경고 사유 (라벨은 messages의 meals.dietary 섹션). */
export type DietaryFlag = 'pork' | 'beef' | 'alcohol' | 'meat' | 'fish_seafood' | 'shellfish'

export const DIETARY_FLAGS: DietaryFlag[] = ['pork', 'beef', 'alcohol', 'meat', 'fish_seafood', 'shellfish']

/** 각 금기가 검사하는 사유 집합. */
const RESTRICTION_TO_FLAGS: Record<DietaryRestriction, DietaryFlag[]> = {
  halal: ['pork', 'alcohol'],
  no_pork: ['pork'],
  no_beef: ['beef'],
  vegetarian: ['meat', 'fish_seafood'],
  kosher: ['pork', 'shellfish'],
}

// ─── 알레르기 코드 기반 신호 (정확) ─────────────────────────
const CODE_PORK = 10
const CODE_BEEF = 16
const CODE_CHICKEN = 15
const CODES_FISH_SEAFOOD = new Set([7, 8, 9, 17, 18]) // 고등어·게·새우·오징어·조개류
const CODES_SHELLFISH = new Set([8, 9, 17, 18])        // 게·새우·오징어·조개류

// ─── 메뉴 이름 키워드 (보조, 한국어 기준) ───────────────────
const KW_PORK = ['돼지', '제육', '돈까스', '돈가스', '햄', '베이컨', '소시지', '순대', '족발', '보쌈', '삼겹', '목살', '탕수육', '비엔나', '돈육']
const KW_BEEF = ['소고기', '쇠고기', '한우', '우삼겹', '사골', '육개장', '장조림', '우둔', '양지', '사태', '우육']
const KW_ALCOHOL = ['맛술', '미림', '미향', '청주', '정종', '와인', '소주', '럼', '사케', '데리야끼', '데리야키', '레드와인']
const KW_CHICKEN_DUCK = ['닭', '치킨', '계육', '삼계', '오리', '훈제오리', '계장']
const KW_FISH_SEAFOOD = [
  '생선', '고등어', '갈치', '명태', '동태', '코다리', '임연수', '삼치', '꽁치', '조기', '멸치',
  '오징어', '새우', '게살', '맛살', '어묵', '참치', '연어', '쥐포', '쭈꾸미', '주꾸미', '낙지',
  '문어', '조개', '바지락', '홍합', '굴', '액젓', '젓갈', '전복', '꼬막', '북어', '황태',
]
const KW_SHELLFISH = ['새우', '게', '게살', '조개', '오징어', '문어', '낙지', '쭈꾸미', '주꾸미', '홍합', '바지락', '굴', '전복', '꼬막']

function nameHas(name: string, keywords: string[]): boolean {
  return keywords.some(kw => name.includes(kw))
}

function hasFlag(flag: DietaryFlag, name: string, allergens: number[]): boolean {
  const codes = new Set(allergens)
  switch (flag) {
    case 'pork':
      return codes.has(CODE_PORK) || nameHas(name, KW_PORK)
    case 'beef':
      return codes.has(CODE_BEEF) || nameHas(name, KW_BEEF)
    case 'alcohol':
      return nameHas(name, KW_ALCOHOL)
    case 'meat':
      return codes.has(CODE_PORK) || codes.has(CODE_BEEF) || codes.has(CODE_CHICKEN)
        || nameHas(name, KW_PORK) || nameHas(name, KW_BEEF) || nameHas(name, KW_CHICKEN_DUCK)
    case 'fish_seafood':
      return [...codes].some(c => CODES_FISH_SEAFOOD.has(c)) || nameHas(name, KW_FISH_SEAFOOD)
    case 'shellfish':
      return [...codes].some(c => CODES_SHELLFISH.has(c)) || nameHas(name, KW_SHELLFISH)
  }
}

/**
 * 한 메뉴(한국어 이름 + 알레르기 코드)가 선택된 금기들에 대해 위반하는 사유 목록.
 * 여러 금기가 같은 사유를 가리키면 한 번만 반환한다.
 */
export function detectDietaryFlags(
  name: string,
  allergens: number[],
  restrictions: DietaryRestriction[],
): DietaryFlag[] {
  if (restrictions.length === 0) return []
  const wanted = new Set<DietaryFlag>()
  for (const r of restrictions) for (const f of RESTRICTION_TO_FLAGS[r]) wanted.add(f)
  return DIETARY_FLAGS.filter(f => wanted.has(f) && hasFlag(f, name, allergens))
}

/**
 * 메뉴 배열에 dietaryFlags를 부여한다. 반드시 번역 전 한국어 이름에 대해 호출할 것.
 * 번역 단계(translateMealCollectionsForLocale)는 dish를 spread로 복사하므로 flag가 보존된다.
 */
export function annotateMealsWithDietaryFlags(
  meals: Meal[],
  restrictions: DietaryRestriction[],
): Meal[] {
  if (restrictions.length === 0) return meals
  return meals.map(meal => ({
    ...meal,
    dishes: meal.dishes.map(dish => annotateDish(dish, restrictions)),
  }))
}

export function annotateMealCollections(
  collections: Meal[][],
  restrictions: DietaryRestriction[],
): Meal[][] {
  if (restrictions.length === 0) return collections
  return collections.map(meals => annotateMealsWithDietaryFlags(meals, restrictions))
}

function annotateDish(dish: MealDish, restrictions: DietaryRestriction[]): MealDish {
  const flags = detectDietaryFlags(dish.name, dish.allergens, restrictions)
  if (flags.length === 0) return dish
  return { ...dish, dietaryFlags: flags }
}
