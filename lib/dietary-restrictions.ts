import type { Locale } from '@/lib/i18n'
import type { Meal, MealDish } from '@/lib/neis'

export const dietaryRestrictionIds = ['halal', 'no_pork', 'no_beef', 'vegetarian', 'kosher'] as const
export type DietaryRestrictionId = (typeof dietaryRestrictionIds)[number]

export interface DietaryWarning {
  id: DietaryRestrictionId
  label: string
  reason: string
  confidence: 'allergen' | 'keyword'
}

type RestrictionCopy = {
  label: string
  reasonAllergen: string
  reasonKeyword: string
}

export const dietaryPreferenceUiCopy: Record<Locale, {
  title: string
  onboardingTitle: string
  description: string
  empty: string
  save: string
  saving: string
  saved: string
}> = {
  ko: {
    title: '종교/식이 금기',
    onboardingTitle: '피해야 할 음식이 있나요?',
    description: '알레르기 코드는 정확히, 메뉴명 키워드는 보조로 확인해 경고를 보여줘요.',
    empty: '선택 안 함',
    save: '저장',
    saving: '저장 중...',
    saved: '저장되었어요.',
  },
  en: {
    title: 'Religious/dietary restrictions',
    onboardingTitle: 'Any foods to avoid?',
    description: 'Warnings use exact allergy codes plus menu-name keywords as a backup.',
    empty: 'None selected',
    save: 'Save',
    saving: 'Saving...',
    saved: 'Saved.',
  },
  zh: {
    title: '宗教/饮食禁忌',
    onboardingTitle: '有需要避免的食物吗？',
    description: '警告会结合准确的过敏代码和菜单名称关键词。',
    empty: '未选择',
    save: '保存',
    saving: '保存中...',
    saved: '已保存。',
  },
  vi: {
    title: 'Kiêng kỵ tôn giáo/ăn uống',
    onboardingTitle: 'Có món nào cần tránh không?',
    description: 'Cảnh báo dùng mã dị ứng chính xác và từ khóa tên món để hỗ trợ.',
    empty: 'Chưa chọn',
    save: 'Lưu',
    saving: 'Đang lưu...',
    saved: 'Đã lưu.',
  },
  ru: {
    title: 'Религиозные/пищевые ограничения',
    onboardingTitle: 'Есть продукты, которых нужно избегать?',
    description: 'Предупреждения используют точные коды аллергенов и ключевые слова в названии блюда.',
    empty: 'Не выбрано',
    save: 'Сохранить',
    saving: 'Сохранение...',
    saved: 'Сохранено.',
  },
  ar: {
    title: 'قيود دينية/غذائية',
    onboardingTitle: 'هل هناك أطعمة يجب تجنبها؟',
    description: 'تستخدم التحذيرات رموز الحساسية الدقيقة وكلمات اسم الطبق كدعم.',
    empty: 'لم يتم الاختيار',
    save: 'حفظ',
    saving: 'جارٍ الحفظ...',
    saved: 'تم الحفظ.',
  },
  fr: {
    title: 'Restrictions religieuses/alimentaires',
    onboardingTitle: 'Y a-t-il des aliments à éviter ?',
    description: 'Les alertes utilisent les codes allergènes exacts et les mots-clés du menu en complément.',
    empty: 'Aucune sélection',
    save: 'Enregistrer',
    saving: 'Enregistrement...',
    saved: 'Enregistré.',
  },
  id: {
    title: 'Pantangan agama/diet',
    onboardingTitle: 'Ada makanan yang perlu dihindari?',
    description: 'Peringatan memakai kode alergi yang tepat dan kata kunci nama menu sebagai bantuan.',
    empty: 'Belum dipilih',
    save: 'Simpan',
    saving: 'Menyimpan...',
    saved: 'Tersimpan.',
  },
  th: {
    title: 'ข้อจำกัดทางศาสนา/อาหาร',
    onboardingTitle: 'มีอาหารที่ต้องหลีกเลี่ยงไหม?',
    description: 'คำเตือนใช้รหัสแพ้อาหารที่แม่นยำและคำสำคัญจากชื่อเมนูช่วยตรวจสอบ',
    empty: 'ยังไม่ได้เลือก',
    save: 'บันทึก',
    saving: 'กำลังบันทึก...',
    saved: 'บันทึกแล้ว',
  },
}

export const dietaryRestrictionCopy: Record<DietaryRestrictionId, Record<Locale, RestrictionCopy>> = {
  halal: {
    ko: { label: '🌙 할랄', reasonAllergen: '돼지고기 알레르기 코드 포함', reasonKeyword: '할랄 금기 가능 메뉴명' },
    en: { label: '🌙 Halal', reasonAllergen: 'Contains pork allergen code', reasonKeyword: 'Menu name may conflict with halal diet' },
    zh: { label: '🌙 清真', reasonAllergen: '包含猪肉过敏代码', reasonKeyword: '菜单名称可能不符合清真饮食' },
    vi: { label: '🌙 Halal', reasonAllergen: 'Có mã dị ứng thịt heo', reasonKeyword: 'Tên món có thể không phù hợp halal' },
    ru: { label: '🌙 Халяль', reasonAllergen: 'Есть код аллергена свинины', reasonKeyword: 'Название блюда может не подходить для халяльного питания' },
    ar: { label: '🌙 حلال', reasonAllergen: 'يحتوي على رمز حساسية لحم الخنزير', reasonKeyword: 'قد لا يناسب اسم الطبق النظام الحلال' },
    fr: { label: '🌙 Halal', reasonAllergen: 'Contient le code allergène porc', reasonKeyword: 'Le nom du plat peut ne pas convenir au régime halal' },
    id: { label: '🌙 Halal', reasonAllergen: 'Memuat kode alergen babi', reasonKeyword: 'Nama menu mungkin tidak sesuai untuk halal' },
    th: { label: '🌙 ฮาลาล', reasonAllergen: 'มีรหัสสารก่อภูมิแพ้เนื้อหมู', reasonKeyword: 'ชื่อเมนูอาจไม่เหมาะกับอาหารฮาลาล' },
  },
  no_pork: {
    ko: { label: '🐷 돼지고기 제외', reasonAllergen: '돼지고기 알레르기 코드 포함', reasonKeyword: '돼지고기 가능 메뉴명' },
    en: { label: '🐷 No pork', reasonAllergen: 'Contains pork allergen code', reasonKeyword: 'Menu name may include pork' },
    zh: { label: '🐷 不吃猪肉', reasonAllergen: '包含猪肉过敏代码', reasonKeyword: '菜单名称可能含猪肉' },
    vi: { label: '🐷 Không thịt heo', reasonAllergen: 'Có mã dị ứng thịt heo', reasonKeyword: 'Tên món có thể có thịt heo' },
    ru: { label: '🐷 Без свинины', reasonAllergen: 'Есть код аллергена свинины', reasonKeyword: 'Название блюда может содержать свинину' },
    ar: { label: '🐷 بدون لحم خنزير', reasonAllergen: 'يحتوي على رمز حساسية لحم الخنزير', reasonKeyword: 'قد يحتوي اسم الطبق على لحم الخنزير' },
    fr: { label: '🐷 Sans porc', reasonAllergen: 'Contient le code allergène porc', reasonKeyword: 'Le nom du plat peut contenir du porc' },
    id: { label: '🐷 Tanpa babi', reasonAllergen: 'Memuat kode alergen babi', reasonKeyword: 'Nama menu mungkin mengandung babi' },
    th: { label: '🐷 ไม่กินหมู', reasonAllergen: 'มีรหัสสารก่อภูมิแพ้เนื้อหมู', reasonKeyword: 'ชื่อเมนูอาจมีหมู' },
  },
  no_beef: {
    ko: { label: '🐮 쇠고기 제외', reasonAllergen: '쇠고기 알레르기 코드 포함', reasonKeyword: '쇠고기 가능 메뉴명' },
    en: { label: '🐮 No beef', reasonAllergen: 'Contains beef allergen code', reasonKeyword: 'Menu name may include beef' },
    zh: { label: '🐮 不吃牛肉', reasonAllergen: '包含牛肉过敏代码', reasonKeyword: '菜单名称可能含牛肉' },
    vi: { label: '🐮 Không thịt bò', reasonAllergen: 'Có mã dị ứng thịt bò', reasonKeyword: 'Tên món có thể có thịt bò' },
    ru: { label: '🐮 Без говядины', reasonAllergen: 'Есть код аллергена говядины', reasonKeyword: 'Название блюда может содержать говядину' },
    ar: { label: '🐮 بدون لحم بقر', reasonAllergen: 'يحتوي على رمز حساسية لحم البقر', reasonKeyword: 'قد يحتوي اسم الطبق على لحم البقر' },
    fr: { label: '🐮 Sans bœuf', reasonAllergen: 'Contient le code allergène bœuf', reasonKeyword: 'Le nom du plat peut contenir du bœuf' },
    id: { label: '🐮 Tanpa sapi', reasonAllergen: 'Memuat kode alergen sapi', reasonKeyword: 'Nama menu mungkin mengandung sapi' },
    th: { label: '🐮 ไม่กินเนื้อวัว', reasonAllergen: 'มีรหัสสารก่อภูมิแพ้เนื้อวัว', reasonKeyword: 'ชื่อเมนูอาจมีเนื้อวัว' },
  },
  vegetarian: {
    ko: { label: '🥗 채식', reasonAllergen: '육류/해산물 알레르기 코드 포함', reasonKeyword: '채식 금기 가능 메뉴명' },
    en: { label: '🥗 Vegetarian', reasonAllergen: 'Contains meat or seafood allergen code', reasonKeyword: 'Menu name may conflict with vegetarian diet' },
    zh: { label: '🥗 素食', reasonAllergen: '包含肉类或海鲜过敏代码', reasonKeyword: '菜单名称可能不符合素食' },
    vi: { label: '🥗 Ăn chay', reasonAllergen: 'Có mã dị ứng thịt hoặc hải sản', reasonKeyword: 'Tên món có thể không phù hợp ăn chay' },
    ru: { label: '🥗 Вегетарианское', reasonAllergen: 'Есть код аллергена мяса или морепродуктов', reasonKeyword: 'Название блюда может не подходить для вегетарианского питания' },
    ar: { label: '🥗 نباتي', reasonAllergen: 'يحتوي على رمز حساسية للحوم أو المأكولات البحرية', reasonKeyword: 'قد لا يناسب اسم الطبق النظام النباتي' },
    fr: { label: '🥗 Végétarien', reasonAllergen: 'Contient un code allergène viande ou fruits de mer', reasonKeyword: 'Le nom du plat peut ne pas convenir au régime végétarien' },
    id: { label: '🥗 Vegetarian', reasonAllergen: 'Memuat kode alergen daging atau makanan laut', reasonKeyword: 'Nama menu mungkin tidak sesuai untuk vegetarian' },
    th: { label: '🥗 มังสวิรัติ', reasonAllergen: 'มีรหัสสารก่อภูมิแพ้เนื้อหรืออาหารทะเล', reasonKeyword: 'ชื่อเมนูอาจไม่เหมาะกับอาหารมังสวิรัติ' },
  },
  kosher: {
    ko: { label: '✡️ 코셔', reasonAllergen: '돼지고기/갑각류/조개류 알레르기 코드 포함', reasonKeyword: '코셔 금기 가능 메뉴명' },
    en: { label: '✡️ Kosher', reasonAllergen: 'Contains pork, shellfish, or crustacean allergen code', reasonKeyword: 'Menu name may conflict with kosher diet' },
    zh: { label: '✡️ 犹太洁食', reasonAllergen: '包含猪肉、贝类或甲壳类过敏代码', reasonKeyword: '菜单名称可能不符合犹太洁食' },
    vi: { label: '✡️ Kosher', reasonAllergen: 'Có mã dị ứng thịt heo, sò ốc hoặc giáp xác', reasonKeyword: 'Tên món có thể không phù hợp kosher' },
    ru: { label: '✡️ Кошерное', reasonAllergen: 'Есть код аллергена свинины, моллюсков или ракообразных', reasonKeyword: 'Название блюда может не подходить для кошерного питания' },
    ar: { label: '✡️ كوشير', reasonAllergen: 'يحتوي على رمز حساسية للخنزير أو المحار أو القشريات', reasonKeyword: 'قد لا يناسب اسم الطبق النظام الكوشير' },
    fr: { label: '✡️ Casher', reasonAllergen: 'Contient un code allergène porc, coquillages ou crustacés', reasonKeyword: 'Le nom du plat peut ne pas convenir au régime casher' },
    id: { label: '✡️ Kosher', reasonAllergen: 'Memuat kode alergen babi, kerang, atau krustasea', reasonKeyword: 'Nama menu mungkin tidak sesuai untuk kosher' },
    th: { label: '✡️ โคเชอร์', reasonAllergen: 'มีรหัสสารก่อภูมิแพ้หมู หอย หรือครัสเตเชียน', reasonKeyword: 'ชื่อเมนูอาจไม่เหมาะกับอาหารโคเชอร์' },
  },
}

const PORK_ALLERGEN = 10
const BEEF_ALLERGEN = 16
const MEAT_OR_SEAFOOD_ALLERGENS = new Set([7, 8, 9, 10, 15, 16, 17, 18])
const KOSHER_ALLERGENS = new Set([8, 9, 10, 18])

const KEYWORDS: Record<DietaryRestrictionId, RegExp> = {
  halal: /돼지|돈육|돈까스|돈가스|제육|햄|베이컨|소시지|소세지|순대|족발|보쌈|탕수육|라드|알코올|와인/i,
  no_pork: /돼지|돈육|돈까스|돈가스|제육|햄|베이컨|소시지|소세지|순대|족발|보쌈|탕수육|라드/i,
  no_beef: /소고기|쇠고기|牛|한우|우육|불고기|갈비|스테이크|비프|사골|육개장|설렁탕/i,
  vegetarian: /고기|돼지|돈육|소고기|쇠고기|한우|우육|닭|치킨|오리|햄|베이컨|소시지|소세지|생선|고등어|명태|오징어|낙지|주꾸미|새우|게|조개|해물|어묵|떡갈비|탕수육|불고기|갈비/i,
  kosher: /돼지|돈육|햄|베이컨|소시지|소세지|새우|게|조개|굴|홍합|전복|해물|갑각|오징어|낙지|주꾸미|알코올|와인/i,
}

export function parseDietaryRestrictions(value: unknown): DietaryRestrictionId[] {
  if (!Array.isArray(value)) return []
  const allowed = new Set<DietaryRestrictionId>(dietaryRestrictionIds)
  return Array.from(new Set(value.filter((item): item is DietaryRestrictionId => allowed.has(item as DietaryRestrictionId))))
}

export function dietaryRestrictionLabel(id: DietaryRestrictionId, locale: Locale): string {
  return dietaryRestrictionCopy[id][locale]?.label ?? dietaryRestrictionCopy[id].ko.label
}

export function detectDietaryWarnings(
  dish: Pick<MealDish, 'name' | 'allergens'>,
  selected: readonly DietaryRestrictionId[],
  locale: Locale,
): DietaryWarning[] {
  const allergenSet = new Set(dish.allergens)
  const warnings: DietaryWarning[] = []

  for (const id of selected) {
    const copy = dietaryRestrictionCopy[id][locale] ?? dietaryRestrictionCopy[id].ko
    const hasAllergen = id === 'halal' || id === 'no_pork'
      ? allergenSet.has(PORK_ALLERGEN)
      : id === 'no_beef'
        ? allergenSet.has(BEEF_ALLERGEN)
        : id === 'vegetarian'
          ? dish.allergens.some(code => MEAT_OR_SEAFOOD_ALLERGENS.has(code))
          : dish.allergens.some(code => KOSHER_ALLERGENS.has(code))

    if (hasAllergen) {
      warnings.push({ id, label: copy.label, reason: copy.reasonAllergen, confidence: 'allergen' })
      continue
    }

    if (KEYWORDS[id].test(dish.name)) {
      warnings.push({ id, label: copy.label, reason: copy.reasonKeyword, confidence: 'keyword' })
    }
  }

  return warnings
}

export function annotateMealsWithDietaryWarnings(
  meals: Meal[],
  selected: readonly DietaryRestrictionId[],
  locale: Locale,
): Meal[] {
  if (selected.length === 0) return meals
  return meals.map(meal => ({
    ...meal,
    dishes: meal.dishes.map(dish => ({
      ...dish,
      dietaryWarnings: detectDietaryWarnings(dish, selected, locale),
    })),
  }))
}
