/**
 * 시간표 과목명 정적 사전 (Tier 1).
 *
 * NEIS에서 한글로 들어오는 시간표 과목명을 5개 언어(en/zh/ar/ru/vi)로 미리 매핑해 둔
 * 큐레이션 사전이다. 사전에 적중하면 즉시·무비용으로 번역되고, 없는 과목은
 * `lib/subject-translation.ts`의 Tier 2(즉석 번역 + DB 캐시)로 넘어간다.
 *
 * 설계 메모:
 * - 한국 고유 과목(국어/한국사/한문)은 "정확한 의미"로 번역한다(현지 동일 슬롯 치환 금지).
 * - 도덕·윤리류는 세속/시민윤리 표현을 쓴다(아랍어: 종교 프레이밍 금지).
 * - 비수업 칸(공강·점심·자습·청소·조회/종례 등)도 번역 대상이다.
 * - `// ⚠` 주석은 네이티브 검수 후 확정 권장 항목.
 *
 * fr/id/th는 의도적으로 비워 둔다 → 해당 로케일은 Tier 2(LLM)로 처리된다.
 *
 * @see lib/neis.ts ALLERGEN_NAMES — 동일한 "코드 상수" 컨벤션.
 */

import type { Locale } from '@/lib/i18n'

type SubjectTranslation = Partial<Record<Locale, string>>

/** 정규화된 한글 base(키는 가독성 위해 자연 표기) → 언어별 번역. */
export const SUBJECT_TRANSLATIONS: Record<string, SubjectTranslation> = {
  // ── 핵심 과목 ─────────────────────────────────────────────
  국어: { en: 'Korean', zh: '韩国语', ar: 'اللغة الكورية', ru: 'Корейский язык', vi: 'Tiếng Hàn' },
  수학: { en: 'Math', zh: '数学', ar: 'الرياضيات', ru: 'Математика', vi: 'Toán' },
  영어: { en: 'English', zh: '英语', ar: 'اللغة الإنجليزية', ru: 'Английский язык', vi: 'Tiếng Anh' },
  과학: { en: 'Science', zh: '科学', ar: 'العلوم', ru: 'Естествознание', vi: 'Khoa học' },
  사회: { en: 'Social Studies', zh: '社会', ar: 'الدراسات الاجتماعية', ru: 'Окружающий мир', vi: 'Xã hội' },
  도덕: { en: 'Moral Education', zh: '道德与法治', ar: 'التربية الأخلاقية', ru: 'Основы светской этики', vi: 'Đạo đức' },
  체육: { en: 'PE', zh: '体育', ar: 'التربية البدنية', ru: 'Физкультура', vi: 'Thể dục' },
  음악: { en: 'Music', zh: '音乐', ar: 'الموسيقى', ru: 'Музыка', vi: 'Âm nhạc' },
  미술: { en: 'Art', zh: '美术', ar: 'التربية الفنية', ru: 'Изобразительное искусство', vi: 'Mỹ thuật' },
  역사: { en: 'History', zh: '历史', ar: 'التاريخ', ru: 'История', vi: 'Lịch sử' },
  한국사: { en: 'Korean History', zh: '韩国历史', ar: 'التاريخ الكوري', ru: 'История Кореи', vi: 'Lịch sử Hàn Quốc' },
  한문: { en: 'Classical Chinese', zh: '汉文', ar: 'الحروف الصينية الكلاسيكية', ru: 'Классический китайский', vi: 'Hán văn' },
  실과: { en: 'Practical Arts', zh: '劳动', ar: 'الأشغال اليدوية والمنزلية', ru: 'Технология', vi: 'Công nghệ' },
  '기술·가정': { en: 'Technology and Home Economics', zh: '技术与生活', ar: 'التكنولوجيا والعلوم المنزلية', ru: 'Технология', vi: 'Công nghệ - Gia đình' },
  정보: { en: 'Computer Science', zh: '信息技术', ar: 'المعلوماتية', ru: 'Информатика', vi: 'Tin học' },
  보건: { en: 'Health', zh: '健康教育', ar: 'التربية الصحية', ru: 'ОБЖ', vi: 'Giáo dục sức khỏe' },
  환경: { en: 'Environment', zh: '环境教育', ar: 'العلوم البيئية', ru: 'Экология', vi: 'Môi trường' },
  진로: { en: 'Career Education', zh: '生涯规划', ar: 'التوجيه المهني', ru: 'Профориентация', vi: 'Hướng nghiệp' },

  // ── 초등 통합교과 (1–2학년) ────────────────────────────────
  '바른 생활': { en: 'Disciplined Life', zh: '品德与生活', ar: 'الحياة الصحيحة', ru: 'Правила жизни', vi: 'Đạo đức sống' },
  '슬기로운 생활': { en: 'Wise Life', zh: '生活实践', ar: 'الحياة الذكية', ru: 'Познание мира', vi: 'Khoa học sống' },
  '즐거운 생활': { en: 'Joyful Life', zh: '艺术与生活', ar: 'الحياة السعيدة', ru: 'Творчество', vi: 'Nghệ thuật sống' },
  '안전한 생활': { en: 'Safe Life', zh: '安全教育', ar: 'الحياة الآمنة', ru: 'Основы безопасности', vi: 'An toàn học đường' },
  봄: { en: 'Spring', zh: '春', ar: 'فصل الربيع', ru: 'Весна', vi: 'Mùa xuân' }, // ⚠ zh 검수
  여름: { en: 'Summer', zh: '夏', ar: 'فصل الصيف', ru: 'Лето', vi: 'Mùa hè' }, // ⚠ zh 검수
  가을: { en: 'Autumn', zh: '秋', ar: 'فصل الخريف', ru: 'Осень', vi: 'Mùa thu' }, // ⚠ zh 검수
  겨울: { en: 'Winter', zh: '冬', ar: 'فصل الشتاء', ru: 'Зима', vi: 'Mùa đông' }, // ⚠ zh 검수

  // ── 고교 과학 ─────────────────────────────────────────────
  물리학: { en: 'Physics', zh: '物理', ar: 'الفيزياء', ru: 'Физика', vi: 'Vật lý' },
  화학: { en: 'Chemistry', zh: '化学', ar: 'الكيمياء', ru: 'Химия', vi: 'Hóa học' },
  생명과학: { en: 'Biology', zh: '生物', ar: 'علم الأحياء', ru: 'Биология', vi: 'Sinh học' },
  지구과학: { en: 'Earth Science', zh: '地球科学', ar: 'العلوم الأرضية', ru: 'География', vi: 'Khoa học trái đất' }, // ⚠ ru 검수
  통합과학: { en: 'Integrated Science', zh: '综合科学', ar: 'العلوم المتكاملة', ru: 'Естествознание', vi: 'Khoa học tổng hợp' },

  // ── 고교 사회 ─────────────────────────────────────────────
  통합사회: { en: 'Integrated Social Studies', zh: '综合社会', ar: 'الدراسات الاجتماعية المتكاملة', ru: 'Обществознание', vi: 'Xã hội tổng hợp' },
  한국지리: { en: 'Korean Geography', zh: '韩国地理', ar: 'جغرافيا كوريا', ru: 'География Кореи', vi: 'Địa lý Hàn Quốc' },
  세계지리: { en: 'World Geography', zh: '世界地理', ar: 'الجغرافيا العالمية', ru: 'География', vi: 'Địa lý thế giới' },
  세계사: { en: 'World History', zh: '世界历史', ar: 'التاريخ العالمي', ru: 'Всемирная история', vi: 'Lịch sử thế giới' },
  동아시아사: { en: 'East Asian History', zh: '东亚历史', ar: 'تاريخ شرق آسيا', ru: 'История Восточной Азии', vi: 'Lịch sử Đông Á' },
  경제: { en: 'Economics', zh: '经济', ar: 'الاقتصاد', ru: 'Экономика', vi: 'Kinh tế' },
  '정치와 법': { en: 'Politics and Law', zh: '政治与法律', ar: 'السياسة والقانون', ru: 'Право', vi: 'Chính trị - Pháp luật' },
  '사회·문화': { en: 'Society and Culture', zh: '社会与文化', ar: 'المجتمع والثقافة', ru: 'Обществознание', vi: 'Xã hội - Văn hóa' },
  '생활과 윤리': { en: 'Ethics and Life', zh: '伦理与生活', ar: 'الأخلاق والحياة اليومية', ru: 'Основы морали', vi: 'Cuộc sống và đạo đức' },
  '윤리와 사상': { en: 'Ethics and Thought', zh: '伦理与思想', ar: 'الأخلاق والفكر', ru: 'Основы философии', vi: 'Đạo đức - Tư tưởng' },

  // ── 고교 수학·국어 심화 ────────────────────────────────────
  미적분: { en: 'Calculus', zh: '微积分', ar: 'حساب التفاضل والتكامل', ru: 'Математический анализ', vi: 'Giải tích' },
  '확률과 통계': { en: 'Probability and Statistics', zh: '概率与统计', ar: 'الإحصاء والاحتمالات', ru: 'Теория вероятностей', vi: 'Xác suất - Thống kê' },
  기하: { en: 'Geometry', zh: '几何', ar: 'الهندسة', ru: 'Геометрия', vi: 'Hình học' },
  문학: { en: 'Literature', zh: '文学', ar: 'الأدب', ru: 'Литература', vi: 'Văn học' },
  독서: { en: 'Reading', zh: '阅读', ar: 'المطالعة', ru: 'Чтение', vi: 'Đọc hiểu' },
  '화법과 작문': { en: 'Speech and Composition', zh: '写作与表达', ar: 'التحدث والكتابة', ru: 'Развитие речи', vi: 'Nói - Viết' },
  '언어와 매체': { en: 'Language and Media', zh: '语言与传播', ar: 'اللغة والإعلام', ru: 'Язык и медиа', vi: 'Ngôn ngữ - Phương tiện' },

  // ── 제2외국어 ─────────────────────────────────────────────
  중국어: { en: 'Chinese', zh: '中文', ar: 'اللغة الصينية', ru: 'Китайский язык', vi: 'Tiếng Trung Quốc' },
  일본어: { en: 'Japanese', zh: '日语', ar: 'اللغة اليابانية', ru: 'Японский язык', vi: 'Tiếng Nhật' },
  독일어: { en: 'German', zh: '德语', ar: 'اللغة الألمانية', ru: 'Немецкий язык', vi: 'Tiếng Đức' },
  프랑스어: { en: 'French', zh: '法语', ar: 'اللغة الفرنسية', ru: 'Французский язык', vi: 'Tiếng Pháp' },
  스페인어: { en: 'Spanish', zh: '西班牙语', ar: 'اللغة الإسبانية', ru: 'Испанский язык', vi: 'Tiếng Tây Ban Nha' },
  러시아어: { en: 'Russian', zh: '俄语', ar: 'اللغة الروسية', ru: 'Русский язык', vi: 'Tiếng Nga' },
  베트남어: { en: 'Vietnamese', zh: '越南语', ar: 'اللغة الفيتنامية', ru: 'Вьетнамский язык', vi: 'Tiếng Việt' },
  아랍어: { en: 'Arabic', zh: '阿拉伯语', ar: 'اللغة العربية', ru: 'Арабский язык', vi: 'Tiếng Ả Rập' },

  // ── 창체·비수업 칸·활동 ────────────────────────────────────
  '창의적 체험활동': { en: 'Creative Experiential Activities', zh: '创意实践活动', ar: 'الأنشطة التجريبية الإبداعية', ru: 'Внеурочная деятельность', vi: 'Hoạt động trải nghiệm sáng tạo' },
  자율활동: { en: 'Autonomous Activity', zh: '自主活动', ar: 'الأنشطة الذاتية', ru: 'Самостоятельная деятельность', vi: 'Hoạt động tự chủ' },
  동아리활동: { en: 'Club Activity', zh: '社团活动', ar: 'النشاط النادي', ru: 'Кружок', vi: 'Hoạt động câu lạc bộ' },
  봉사활동: { en: 'Volunteer Activity', zh: '志愿服务', ar: 'النشاط التطوعي', ru: 'Волонтёрская деятельность', vi: 'Hoạt động tình nguyện' },
  자습: { en: 'Self-Study', zh: '自习', ar: 'الدراسة الذاتية', ru: 'Самоподготовка', vi: 'Tự học' },
  공강: { en: 'Free Period', zh: '空课', ar: 'فترة حرة', ru: 'Окно', vi: 'Giờ trống' },
  점심: { en: 'Lunch', zh: '午餐', ar: 'الغداء', ru: 'Обед', vi: 'Giờ ăn trưa' },
  청소: { en: 'Cleaning', zh: '卫生', ar: 'وقت التنظيف', ru: 'Уборка', vi: 'Vệ sinh lớp' },
  조회: { en: 'Morning Assembly', zh: '班会', ar: 'طابور الصباح', ru: 'Линейка', vi: 'Họp sáng' }, // ⚠ vi 검수
  종례: { en: 'Closing Meeting', zh: '班级总结', ar: 'الاصطفاف الختامي', ru: 'Классный час', vi: 'Họp chiều' }, // ⚠ vi 검수
  재량활동: { en: 'Discretionary Activity', zh: '自主实践', ar: 'النشاط التقديري', ru: 'Факультатив', vi: 'Hoạt động tự chọn' },
  토론: { en: 'Debate', zh: '辩论', ar: 'النقاش والحوار', ru: 'Дискуссия', vi: 'Thảo luận' },
  논술: { en: 'Essay Writing', zh: '写作', ar: 'الكتابة الإنشائية', ru: 'Сочинение', vi: 'Viết luận' },
  방과후: { en: 'After-School', zh: '课后活动', ar: 'برنامج بعد الدوام', ru: 'Внеклассная деятельность', vi: 'Chương trình ngoài giờ học' },
}

/** 약어/동의어 → 정식 키. 값은 SUBJECT_TRANSLATIONS의 키와 일치해야 한다. */
export const SUBJECT_ABBREVIATIONS: Record<string, string> = {
  창체: '창의적 체험활동',
  기가: '기술·가정',
  물리: '물리학',
  사문: '사회·문화',
  생윤: '생활과 윤리',
  확통: '확률과 통계',
  중식: '점심',
  자율학습: '자습',
  '진로와 직업': '진로',
}

/** 가운뎃점·공백 등 표기 변형을 제거한 조회용 키. ('기술·가정'/'기술가정' → 동일) */
function normalizeKey(value: string): string {
  return value
    .normalize('NFC')
    .replace(/[\s·・∙ㆍ]/g, '')
}

// 사전/약어를 정규화 키로 색인 (모듈 로드 시 1회).
const NORMALIZED_INDEX = new Map<string, SubjectTranslation>()
for (const [key, value] of Object.entries(SUBJECT_TRANSLATIONS)) {
  NORMALIZED_INDEX.set(normalizeKey(key), value)
}
const NORMALIZED_ABBREV = new Map<string, string>()
for (const [abbr, canonical] of Object.entries(SUBJECT_ABBREVIATIONS)) {
  NORMALIZED_ABBREV.set(normalizeKey(abbr), normalizeKey(canonical))
}

const ROMAN_NUMERALS: Record<string, string> = {
  Ⅰ: 'I', Ⅱ: 'II', Ⅲ: 'III', Ⅳ: 'IV', Ⅴ: 'V',
}

/**
 * 과목명에서 끝의 레벨 표기(로마 Ⅰ/Ⅱ/Ⅲ 또는 숫자 1~5)를 분리한다.
 * 예: '수학Ⅱ' → { base: '수학', suffix: 'II' }, '영어 1' → { base: '영어', suffix: '1' }
 */
export function splitSubjectSuffix(raw: string): { base: string; suffix: string } {
  const trimmed = raw.normalize('NFC').trim()
  const match = trimmed.match(/^(.*?)[\s]*([ⅠⅡⅢⅣⅤ]|[1-5])$/)
  if (!match || !match[1].trim()) return { base: trimmed, suffix: '' }
  const rawSuffix = match[2]
  return { base: match[1].trim(), suffix: ROMAN_NUMERALS[rawSuffix] ?? rawSuffix }
}

/** 번역된 base에 레벨 접미사를 다시 붙인다. ('Math' + 'II' → 'Math II') */
export function applySubjectSuffix(translatedBase: string, suffix: string): string {
  return suffix ? `${translatedBase} ${suffix}` : translatedBase
}

/**
 * 정적 사전으로 과목명을 번역한다(약어·레벨접미사·표기변형 정규화 포함).
 * 적중하면 번역 문자열을, 사전에 없으면 null을 반환한다.
 */
export function resolveStaticSubject(raw: string, locale: Locale): string | null {
  const { base, suffix } = splitSubjectSuffix(raw)
  let key = normalizeKey(base)
  key = NORMALIZED_ABBREV.get(key) ?? key
  const translated = NORMALIZED_INDEX.get(key)?.[locale]
  if (!translated) return null
  return applySubjectSuffix(translated, suffix)
}
