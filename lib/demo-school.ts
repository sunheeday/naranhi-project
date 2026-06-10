import 'server-only'

import { createHash } from 'node:crypto'
import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database, Json } from '@/types/database'

export const DEMO_SCHOOL_NAME = 'Naranhi School'
export const DEMO_SCHOOL_LEVEL = 'Demo'
export const DEMO_SCHOOL_ADDRESS = 'Seoul Demo Campus, 101 Story Lane'
export const DEMO_SCHOOL_OFFICE_CODE = 'DEMO'
export const DEMO_SCHOOL_CODE = 'NARANHI001'
export const DEMO_SCHOOL_HOMEPAGE_URL = 'https://demo.naranhi.school'
export const DEMO_MEAL_DONOR_SCHOOL_NAMES = ['부천부흥초등학교', '부천부흥초']
export const DEMO_NOTICE_DONOR_SCHOOL_NAMES = ['부천부흥초등학교', '부천부흥초']
const DEMO_MEAL_SEED_WINDOW_DAYS = 21
const DEMO_NOTICE_REUSE_LIMIT = 5

type ServiceClient = SupabaseClient<Database>

type NoticeRow = Database['public']['Tables']['notices']['Row']
type NoticeTranslationRow = Database['public']['Tables']['notice_ai_translations']['Row']
type NoticeCardRow = Database['public']['Tables']['notice_cards']['Row']
type NoticeCardTranslationRow = Database['public']['Tables']['notice_card_translations']['Row']
type SchoolEventRow = Database['public']['Tables']['school_events']['Row']

interface DemoSchoolSearchResult {
  name: string
  level: string
  officeCode: string
  schoolCode: string
  address: string
  homepageUrl: string
}

interface DemoNoticeSeed {
  id: string
  detailUrl: string
  sourcePostUid?: string
  titleKo: string
  translatedTitle: Record<string, string>
  originalText: string
  translatedBody: Record<string, string>
  summaryKo: string
  translatedSummary: Record<string, string>
  refinedBodyKo: string
  translatedSourceBody: Record<string, string>
  dueDate: string | null
  eventDates: string[]
  eventLocation: string | null
  crawlResult?: Json
  attachmentSources?: Array<{
    sourceType: 'attachment'
    filename: string
    originUrl: string
    fixturePath: string
    fileType: 'pdf' | 'hwp' | 'hwpx'
    refinedTextKo?: string
    translatedText?: Record<string, string>
    needsFile?: boolean
  }>
  cards: Array<{
    id: string
    type: 'action' | 'schedule' | 'supplies'
    order: number
    koItems: Array<{ text: string; hint?: string }>
    translatedItems: Record<string, Array<{ text: string; hint?: string }>>
  }>
}

const DEMO_LANGUAGES = ['en', 'ar', 'ru'] as const

const DEMO_SCHOOL_SEARCH_RESULT: DemoSchoolSearchResult = {
  name: DEMO_SCHOOL_NAME,
  level: DEMO_SCHOOL_LEVEL,
  officeCode: DEMO_SCHOOL_OFFICE_CODE,
  schoolCode: DEMO_SCHOOL_CODE,
  address: DEMO_SCHOOL_ADDRESS,
  homepageUrl: DEMO_SCHOOL_HOMEPAGE_URL,
}

const DEMO_NOTICE_SEEDS: DemoNoticeSeed[] = [
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2001',
    detailUrl: 'demo://naranhi-school/fall-family-night',
    titleKo: '가을 가족의 밤 참가 안내',
    translatedTitle: {
      en: 'Invitation to Autumn Family Night',
      ar: 'دعوة إلى أمسية الأسرة الخريفية',
      ru: 'Приглашение на Осенний семейный вечер',
    },
    originalText:
      '가을 가족의 밤 행사가 2026년 9월 18일 금요일 오후 6시에 체육관에서 열립니다.\n' +
      '참가를 원하는 가정은 9월 12일까지 앱에서 참석 여부를 제출해 주세요.\n' +
      '학생은 실내화를, 보호자는 개인 텀블러를 준비해 주세요.',
    translatedBody: {
      en:
        'Autumn Family Night will be held in the gym at 6:00 PM on Friday, September 18, 2026.\n' +
        'Families who wish to join should submit their attendance in the app by September 12.\n' +
        'Students should bring indoor shoes, and guardians should bring a personal tumbler.',
      ar:
        'ستقام أمسية الأسرة الخريفية في الصالة الرياضية الساعة 6:00 مساءً يوم الجمعة 18 سبتمبر 2026.\n' +
        'يُرجى من العائلات الراغبة في المشاركة إرسال تأكيد الحضور عبر التطبيق قبل 12 سبتمبر.\n' +
        'يجب على الطلاب إحضار أحذية داخلية، وعلى أولياء الأمور إحضار كوب شخصي.',
      ru:
        'Осенний семейный вечер пройдет в спортзале в пятницу, 18 сентября 2026 года, в 18:00.\n' +
        'Семьям, которые хотят участвовать, нужно подтвердить участие в приложении до 12 сентября.\n' +
        'Ученикам нужно принести сменную обувь, а родителям — личный термостакан.',
    },
    summaryKo: '9월 18일 가족 행사에 참석 여부를 제출하고 실내화와 텀블러를 준비해 주세요.',
    translatedSummary: {
      en: 'Please submit your attendance for the September 18 family event and prepare indoor shoes and a tumbler.',
      ar: 'يُرجى إرسال تأكيد الحضور لفعالية الأسرة في 18 سبتمبر وتجهيز الأحذية الداخلية والكوب.',
      ru: 'Подтвердите участие в семейном мероприятии 18 сентября и подготовьте сменную обувь и термостакан.',
    },
    refinedBodyKo:
      '행사 일시: 2026년 9월 18일 금요일 오후 6시\n' +
      '장소: 체육관\n' +
      '제출 마감: 2026년 9월 12일\n' +
      '준비물: 학생 실내화, 보호자 개인 텀블러',
    translatedSourceBody: {
      en:
        'Event time: Friday, September 18, 2026 at 6:00 PM\n' +
        'Location: Gym\n' +
        'Submission deadline: September 12, 2026\n' +
        'Items to bring: Indoor shoes for students, personal tumbler for guardians',
      ar:
        'موعد الفعالية: الجمعة 18 سبتمبر 2026 الساعة 6:00 مساءً\n' +
        'المكان: الصالة الرياضية\n' +
        'آخر موعد للتقديم: 12 سبتمبر 2026\n' +
        'المستلزمات: أحذية داخلية للطلاب وكوب شخصي لأولياء الأمور',
      ru:
        'Время мероприятия: пятница, 18 сентября 2026 года, 18:00\n' +
        'Место: спортзал\n' +
        'Срок подачи ответа: 12 сентября 2026 года\n' +
        'Что принести: сменная обувь для учеников и личный термостакан для родителей',
    },
    dueDate: '2026-09-12',
    eventDates: ['2026-09-18'],
    eventLocation: '체육관',
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4001',
        type: 'action',
        order: 0,
        koItems: [{ text: '앱에서 참석 여부 제출', hint: '2026-09-12' }],
        translatedItems: {
          en: [{ text: 'Submit attendance in the app', hint: '2026-09-12' }],
          ar: [{ text: 'أرسل تأكيد الحضور في التطبيق', hint: '2026-09-12' }],
          ru: [{ text: 'Подтвердите участие в приложении', hint: '2026-09-12' }],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4002',
        type: 'schedule',
        order: 1,
        koItems: [
          { text: '행사일: 2026-09-18', hint: '18:00' },
          { text: '장소: 체육관' },
        ],
        translatedItems: {
          en: [
            { text: 'Event date: 2026-09-18', hint: '18:00' },
            { text: 'Location: Gym' },
          ],
          ar: [
            { text: 'تاريخ الفعالية: 2026-09-18', hint: '18:00' },
            { text: 'المكان: الصالة الرياضية' },
          ],
          ru: [
            { text: 'Дата мероприятия: 2026-09-18', hint: '18:00' },
            { text: 'Место: спортзал' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4003',
        type: 'supplies',
        order: 2,
        koItems: [
          { text: '학생 실내화' },
          { text: '보호자 개인 텀블러' },
        ],
        translatedItems: {
          en: [
            { text: 'Indoor shoes for students' },
            { text: 'Personal tumbler for guardians' },
          ],
          ar: [
            { text: 'أحذية داخلية للطلاب' },
            { text: 'كوب شخصي لأولياء الأمور' },
          ],
          ru: [
            { text: 'Сменная обувь для учеников' },
            { text: 'Личный термостакан для родителей' },
          ],
        },
      },
    ],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2002',
    detailUrl: 'demo://naranhi-school/reading-passport',
    titleKo: '여름 독서 여권 챌린지 안내',
    translatedTitle: {
      en: 'Summer Reading Passport Challenge',
      ar: 'تحدي جواز القراءة الصيفي',
      ru: 'Летний читательский паспорт',
    },
    originalText:
      '여름방학 독서 챌린지가 2026년 7월 6일부터 7월 24일까지 진행됩니다.\n' +
      '학생은 매주 2권 이상 읽고 독서 여권에 기록해야 합니다.\n' +
      '첫 주에는 독서 여권과 필통을 준비해 주세요.',
    translatedBody: {
      en:
        'The summer reading challenge will run from July 6 to July 24, 2026.\n' +
        'Students should read at least two books each week and record them in the reading passport.\n' +
        'For the first week, please prepare the reading passport and a pencil case.',
      ar:
        'سيستمر تحدي القراءة الصيفي من 6 يوليو إلى 24 يوليو 2026.\n' +
        'يجب على الطلاب قراءة كتابين على الأقل كل أسبوع وتسجيلهما في جواز القراءة.\n' +
        'في الأسبوع الأول، يُرجى تجهيز جواز القراءة والمقلمة.',
      ru:
        'Летний читательский челлендж пройдет с 6 по 24 июля 2026 года.\n' +
        'Ученикам нужно читать не менее двух книг в неделю и записывать их в читательский паспорт.\n' +
        'На первую неделю подготовьте читательский паспорт и пенал.',
    },
    summaryKo: '7월 독서 챌린지 기간 동안 매주 2권을 읽고 독서 여권을 기록해 주세요.',
    translatedSummary: {
      en: 'During the July reading challenge, read two books each week and record them in the reading passport.',
      ar: 'خلال تحدي القراءة في يوليو، اقرأ كتابين كل أسبوع وسجلهما في جواز القراءة.',
      ru: 'Во время июльского читательского челленджа читайте по две книги в неделю и записывайте их в читательский паспорт.',
    },
    refinedBodyKo:
      '운영 기간: 2026년 7월 6일 ~ 2026년 7월 24일\n' +
      '해야 할 일: 매주 2권 읽기, 독서 여권 기록\n' +
      '첫 주 준비물: 독서 여권, 필통',
    translatedSourceBody: {
      en:
        'Program period: July 6, 2026 to July 24, 2026\n' +
        'To do: Read two books each week, record them in the reading passport\n' +
        'First-week supplies: Reading passport, pencil case',
      ar:
        'مدة البرنامج: من 6 يوليو 2026 إلى 24 يوليو 2026\n' +
        'المهام: قراءة كتابين كل أسبوع وتسجيلهما في جواز القراءة\n' +
        'مستلزمات الأسبوع الأول: جواز القراءة، المقلمة',
      ru:
        'Срок программы: с 6 июля 2026 года по 24 июля 2026 года\n' +
        'Что сделать: читать по две книги в неделю и записывать их в читательский паспорт\n' +
        'Принадлежности на первую неделю: читательский паспорт, пенал',
    },
    dueDate: '2026-07-24',
    eventDates: ['2026-07-06', '2026-07-24'],
    eventLocation: null,
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4011',
        type: 'action',
        order: 0,
        koItems: [
          { text: '매주 2권 이상 읽기' },
          { text: '독서 여권에 기록하기', hint: '2026-07-24' },
        ],
        translatedItems: {
          en: [
            { text: 'Read at least two books each week' },
            { text: 'Record them in the reading passport', hint: '2026-07-24' },
          ],
          ar: [
            { text: 'اقرأ كتابين على الأقل كل أسبوع' },
            { text: 'سجّلها في جواز القراءة', hint: '2026-07-24' },
          ],
          ru: [
            { text: 'Читайте не менее двух книг в неделю' },
            { text: 'Записывайте их в читательский паспорт', hint: '2026-07-24' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4012',
        type: 'schedule',
        order: 1,
        koItems: [
          { text: '운영 시작: 2026-07-06' },
          { text: '기록 마감: 2026-07-24' },
        ],
        translatedItems: {
          en: [
            { text: 'Program starts: 2026-07-06' },
            { text: 'Recording deadline: 2026-07-24' },
          ],
          ar: [
            { text: 'بداية البرنامج: 2026-07-06' },
            { text: 'آخر موعد للتسجيل: 2026-07-24' },
          ],
          ru: [
            { text: 'Начало программы: 2026-07-06' },
            { text: 'Срок записи: 2026-07-24' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4013',
        type: 'supplies',
        order: 2,
        koItems: [{ text: '독서 여권' }, { text: '필통' }],
        translatedItems: {
          en: [{ text: 'Reading passport' }, { text: 'Pencil case' }],
          ar: [{ text: 'جواز القراءة' }, { text: 'المقلمة' }],
          ru: [{ text: 'Читательский паспорт' }, { text: 'Пенал' }],
        },
      },
    ],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2003',
    detailUrl: 'demo://naranhi-school/safety-drill',
    titleKo: '폭우 대비 안전 대피 훈련 안내',
    translatedTitle: {
      en: 'Heavy Rain Safety Drill Notice',
      ar: 'إشعار تدريب الإخلاء للسلامة أثناء الأمطار الغزيرة',
      ru: 'Сообщение об учениях по эвакуации при сильном дожде',
    },
    originalText:
      '폭우 대비 안전 대피 훈련이 2026년 6월 15일 오전 10시에 진행됩니다.\n' +
      '학생은 알림장을 확인하고 우비 또는 얇은 겉옷을 준비해 주세요.\n' +
      '보호자는 당일 비상 연락 가능 여부를 오전 8시 30분까지 확인해 주세요.',
    translatedBody: {
      en:
        'A heavy rain safety drill will take place at 10:00 AM on June 15, 2026.\n' +
        'Students should check their school planner and prepare a raincoat or a light outer layer.\n' +
        'Guardians should confirm emergency contact availability by 8:30 AM on the same day.',
      ar:
        'سيُجرى تدريب السلامة أثناء الأمطار الغزيرة في 15 يونيو 2026 الساعة 10:00 صباحًا.\n' +
        'يجب على الطلاب التحقق من دفتر الملاحظات المدرسي وتجهيز معطف مطر أو سترة خفيفة.\n' +
        'يُرجى من أولياء الأمور تأكيد إمكانية التواصل في الطوارئ بحلول الساعة 8:30 صباحًا في اليوم نفسه.',
      ru:
        'Учения по безопасности при сильном дожде пройдут 15 июня 2026 года в 10:00.\n' +
        'Ученикам нужно проверить школьный дневник и подготовить дождевик или легкую куртку.\n' +
        'Родителям нужно подтвердить доступность для экстренной связи до 8:30 утра в этот день.',
    },
    summaryKo: '6월 15일 안전 대피 훈련 전 학생 준비물과 보호자 연락 확인이 필요합니다.',
    translatedSummary: {
      en: 'Before the June 15 safety drill, students need to prepare rain gear and guardians need to confirm contact availability.',
      ar: 'قبل تدريب السلامة في 15 يونيو، يجب على الطلاب تجهيز مستلزمات المطر وعلى أولياء الأمور تأكيد إمكانية التواصل.',
      ru: 'Перед учениями 15 июня ученикам нужно подготовить дождевик, а родителям — подтвердить доступность для связи.',
    },
    refinedBodyKo:
      '훈련 일정: 2026년 6월 15일 오전 10시\n' +
      '보호자 확인 마감: 2026년 6월 15일 오전 8시 30분\n' +
      '준비물: 우비 또는 얇은 겉옷',
    translatedSourceBody: {
      en:
        'Drill schedule: June 15, 2026 at 10:00 AM\n' +
        'Guardian confirmation deadline: June 15, 2026 at 8:30 AM\n' +
        'Supplies: Raincoat or light outer layer',
      ar:
        'موعد التدريب: 15 يونيو 2026 الساعة 10:00 صباحًا\n' +
        'آخر موعد لتأكيد أولياء الأمور: 15 يونيو 2026 الساعة 8:30 صباحًا\n' +
        'المستلزمات: معطف مطر أو سترة خفيفة',
      ru:
        'Время учений: 15 июня 2026 года в 10:00\n' +
        'Срок подтверждения для родителей: 15 июня 2026 года до 8:30\n' +
        'Что подготовить: дождевик или легкую куртку',
    },
    dueDate: '2026-06-15',
    eventDates: ['2026-06-15'],
    eventLocation: '운동장',
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4021',
        type: 'action',
        order: 0,
        koItems: [{ text: '비상 연락 가능 여부 확인', hint: '2026-06-15 08:30' }],
        translatedItems: {
          en: [{ text: 'Confirm emergency contact availability', hint: '2026-06-15 08:30' }],
          ar: [{ text: 'أكد إمكانية التواصل في الطوارئ', hint: '2026-06-15 08:30' }],
          ru: [{ text: 'Подтвердите доступность для экстренной связи', hint: '2026-06-15 08:30' }],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4022',
        type: 'schedule',
        order: 1,
        koItems: [
          { text: '훈련일: 2026-06-15', hint: '10:00' },
          { text: '장소: 운동장' },
        ],
        translatedItems: {
          en: [
            { text: 'Drill date: 2026-06-15', hint: '10:00' },
            { text: 'Location: Playground' },
          ],
          ar: [
            { text: 'تاريخ التدريب: 2026-06-15', hint: '10:00' },
            { text: 'المكان: ساحة المدرسة' },
          ],
          ru: [
            { text: 'Дата учений: 2026-06-15', hint: '10:00' },
            { text: 'Место: школьный двор' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4023',
        type: 'supplies',
        order: 2,
        koItems: [{ text: '우비 또는 얇은 겉옷' }],
        translatedItems: {
          en: [{ text: 'Raincoat or light outer layer' }],
          ar: [{ text: 'معطف مطر أو سترة خفيفة' }],
          ru: [{ text: 'Дождевик или легкая куртка' }],
        },
      },
    ],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2004',
    detailUrl: 'demo://naranhi-school/parent-volunteer-day',
    titleKo: '학부모 자원봉사 아침 맞이 신청 안내',
    translatedTitle: {
      en: 'Parent Volunteer Morning Welcome Sign-up',
      ar: 'التسجيل في استقبال أولياء الأمور المتطوعين صباحاً',
      ru: 'Запись родителей-волонтеров на утреннюю встречу',
    },
    originalText:
      '학부모 자원봉사 아침 맞이 활동이 2026년 10월 7일부터 10월 9일까지 운영됩니다.\n' +
      '희망하는 보호자는 9월 29일까지 원하는 날짜를 선택해 신청해 주세요.\n' +
      '이름표, 편한 신발, 생수 한 병을 준비해 주세요.',
    translatedBody: {
      en:
        'The parent volunteer morning welcome program will run from October 7 to October 9, 2026.\n' +
        'Guardians who would like to help should select a preferred date and sign up by September 29.\n' +
        'Please prepare a name tag, comfortable shoes, and one bottle of water.',
      ar:
        'سيُقام برنامج استقبال أولياء الأمور المتطوعين صباحاً من 7 أكتوبر إلى 9 أكتوبر 2026.\n' +
        'يُرجى من أولياء الأمور الراغبين في المشاركة اختيار التاريخ المناسب والتسجيل قبل 29 سبتمبر.\n' +
        'يُرجى تجهيز بطاقة اسم وحذاء مريح وزجاجة ماء واحدة.',
      ru:
        'Программа утренней встречи родителей-волонтеров пройдет с 7 по 9 октября 2026 года.\n' +
        'Родителям, желающим участвовать, нужно выбрать удобную дату и записаться до 29 сентября.\n' +
        'Подготовьте бейдж, удобную обувь и бутылку воды.',
    },
    summaryKo: '9월 29일까지 날짜를 선택해 자원봉사 아침 맞이 활동을 신청해 주세요.',
    translatedSummary: {
      en: 'Please choose a date and sign up for the volunteer morning welcome by September 29.',
      ar: 'يُرجى اختيار تاريخ والتسجيل في استقبال المتطوعين الصباحي قبل 29 سبتمبر.',
      ru: 'Выберите дату и запишитесь на утреннюю волонтерскую встречу до 29 сентября.',
    },
    refinedBodyKo:
      '운영 기간: 2026년 10월 7일 ~ 10월 9일\n' +
      '신청 마감: 2026년 9월 29일\n' +
      '준비물: 이름표, 편한 신발, 생수 한 병',
    translatedSourceBody: {
      en:
        'Program dates: October 7 to October 9, 2026\n' +
        'Sign-up deadline: September 29, 2026\n' +
        'Supplies: Name tag, comfortable shoes, one bottle of water',
      ar:
        'فترة البرنامج: من 7 أكتوبر إلى 9 أكتوبر 2026\n' +
        'آخر موعد للتسجيل: 29 سبتمبر 2026\n' +
        'المستلزمات: بطاقة اسم، حذاء مريح، زجاجة ماء واحدة',
      ru:
        'Даты программы: с 7 по 9 октября 2026 года\n' +
        'Срок записи: 29 сентября 2026 года\n' +
        'Принадлежности: бейдж, удобная обувь, бутылка воды',
    },
    dueDate: '2026-09-29',
    eventDates: ['2026-10-07', '2026-10-08', '2026-10-09'],
    eventLocation: '정문',
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4031',
        type: 'action',
        order: 0,
        koItems: [{ text: '희망 날짜 선택 후 신청', hint: '2026-09-29' }],
        translatedItems: {
          en: [{ text: 'Choose a preferred date and sign up', hint: '2026-09-29' }],
          ar: [{ text: 'اختر التاريخ المناسب ثم سجّل', hint: '2026-09-29' }],
          ru: [{ text: 'Выберите удобную дату и запишитесь', hint: '2026-09-29' }],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4032',
        type: 'schedule',
        order: 1,
        koItems: [
          { text: '운영일: 2026-10-07 · 2026-10-09' },
          { text: '장소: 정문' },
        ],
        translatedItems: {
          en: [
            { text: 'Program dates: 2026-10-07 · 2026-10-09' },
            { text: 'Location: Main gate' },
          ],
          ar: [
            { text: 'تواريخ البرنامج: 2026-10-07 · 2026-10-09' },
            { text: 'المكان: البوابة الرئيسية' },
          ],
          ru: [
            { text: 'Даты программы: 2026-10-07 · 2026-10-09' },
            { text: 'Место: главный вход' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4033',
        type: 'supplies',
        order: 2,
        koItems: [{ text: '이름표' }, { text: '편한 신발' }, { text: '생수 한 병' }],
        translatedItems: {
          en: [{ text: 'Name tag' }, { text: 'Comfortable shoes' }, { text: 'One bottle of water' }],
          ar: [{ text: 'بطاقة اسم' }, { text: 'حذاء مريح' }, { text: 'زجاجة ماء واحدة' }],
          ru: [{ text: 'Бейдж' }, { text: 'Удобная обувь' }, { text: 'Бутылка воды' }],
        },
      },
    ],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2008',
    detailUrl: 'demo://naranhi-school/june-academic-calendar',
    titleKo: '6월 학사 일정 안내',
    translatedTitle: {
      en: 'June School Calendar Notice',
      ar: 'إشعار الجدول المدرسي لشهر يونيو',
      ru: 'Уведомление о школьном расписании на июнь',
    },
    originalText:
      '6월 학사 일정을 안내드립니다.\n' +
      '6월 12일 금요일은 공개수업의 날이며, 6월 19일 금요일은 학급 사진 촬영이 진행됩니다.\n' +
      '행사 시간과 장소는 아래 안내를 참고해 주세요.',
    translatedBody: {
      en:
        'Here is the school calendar for June.\n' +
        'Open Class Day will be held on Friday, June 12, and class photo day will take place on Friday, June 19.\n' +
        'Please refer to the information below for the event time and location.',
      ar:
        'إليكم الجدول المدرسي لشهر يونيو.\n' +
        'سيُقام يوم الصف المفتوح يوم الجمعة 12 يونيو، وسيتم تصوير صور الصف يوم الجمعة 19 يونيو.\n' +
        'يُرجى الرجوع إلى المعلومات أدناه لمعرفة وقت ومكان الفعالية.',
      ru:
        'Ниже школьное расписание на июнь.\n' +
        'День открытого класса пройдет в пятницу, 12 июня, а фотосъемка класса состоится в пятницу, 19 июня.\n' +
        'Пожалуйста, смотрите информацию ниже о времени и месте мероприятий.',
    },
    summaryKo: '6월 공개수업과 학급 사진 촬영 일정만 정리한 안내 공지입니다.',
    translatedSummary: {
      en: 'This notice shares the June schedule for open class day and class photo day.',
      ar: 'يشارك هذا الإشعار جدول يونيو ليوم الصف المفتوح ويوم تصوير الصف.',
      ru: 'В этом уведомлении указаны июньские даты дня открытого класса и фотосъемки класса.',
    },
    refinedBodyKo:
      '공개수업: 2026년 6월 12일 금요일 10:00, 2층 열린교실\n' +
      '학급 사진 촬영: 2026년 6월 19일 금요일 09:30, 강당',
    translatedSourceBody: {
      en:
        'Open class: Friday, June 12, 2026 at 10:00, 2F Open Classroom\n' +
        'Class photo day: Friday, June 19, 2026 at 09:30, Auditorium',
      ar:
        'الصف المفتوح: الجمعة 12 يونيو 2026 الساعة 10:00، الفصل المفتوح في الطابق الثاني\n' +
        'تصوير الصف: الجمعة 19 يونيو 2026 الساعة 09:30، القاعة',
      ru:
        'Открытый класс: пятница, 12 июня 2026 года, 10:00, открытый класс на 2-м этаже\n' +
        'Фотосъемка класса: пятница, 19 июня 2026 года, 09:30, актовый зал',
    },
    dueDate: null,
    eventDates: ['2026-06-12', '2026-06-19'],
    eventLocation: '2층 열린교실 / 강당',
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4081',
        type: 'schedule',
        order: 0,
        koItems: [
          { text: '공개수업: 2026-06-12', hint: '10:00 · 2층 열린교실' },
          { text: '학급 사진 촬영: 2026-06-19', hint: '09:30 · 강당' },
        ],
        translatedItems: {
          en: [
            { text: 'Open class: 2026-06-12', hint: '10:00 · 2F Open Classroom' },
            { text: 'Class photo day: 2026-06-19', hint: '09:30 · Auditorium' },
          ],
          ar: [
            { text: 'الصف المفتوح: 2026-06-12', hint: '10:00 · الفصل المفتوح في الطابق الثاني' },
            { text: 'تصوير الصف: 2026-06-19', hint: '09:30 · القاعة' },
          ],
          ru: [
            { text: 'Открытый класс: 2026-06-12', hint: '10:00 · открытый класс на 2-м этаже' },
            { text: 'Фотосъемка класса: 2026-06-19', hint: '09:30 · актовый зал' },
          ],
        },
      },
    ],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2005',
    sourcePostUid: 'bcbh-2026-homepage-signup',
    detailUrl: 'https://www.bcbh.es.kr/board/notice/2026-homepage-signup',
    titleKo: '2026학년도 부천부흥초 홈페이지 가입 안내',
    translatedTitle: {
      en: '2026 Bucheon Buhung Elementary Website Registration Guide',
      ar: 'دليل التسجيل في موقع مدرسة بوشون بوهونغ الابتدائية لعام 2026',
      ru: 'Инструкция по регистрации на сайте начальной школы Пучхон Бухын на 2026 год',
    },
    originalText:
      '2026학년도 부천부흥초 홈페이지 학부모 계정 가입 안내입니다.\n' +
      '보호자는 3월 11일까지 가입을 완료하고 학생 이름을 연동해 주세요.\n' +
      '첨부된 안내문과 가입 매뉴얼 PDF를 확인해 주세요.\n\n2026. 3. 4.\n부천부흥초등학교장',
    translatedBody: {
      en:
        'This is the guide for parent account registration on the Bucheon Buhung Elementary website for the 2026 school year.\n' +
        'Guardians should complete registration and connect the student name by March 11.\n' +
        'Please review the attached guide and the registration manual PDF.',
      ar:
        'هذا هو دليل تسجيل حساب أولياء الأمور في موقع مدرسة بوشون بوهونغ الابتدائية للعام الدراسي 2026.\n' +
        'يُرجى من أولياء الأمور إكمال التسجيل وربط اسم الطالب قبل 11 مارس.\n' +
        'يُرجى مراجعة الدليل المرفق وملف PDF الخاص بإرشادات التسجيل.',
      ru:
        'Это инструкция по регистрации родительской учетной записи на сайте начальной школы Пучхон Бухын на 2026 учебный год.\n' +
        'Родителям нужно завершить регистрацию и привязать имя ученика до 11 марта.\n' +
        'Пожалуйста, ознакомьтесь с приложенной инструкцией и PDF-руководством по регистрации.',
    },
    summaryKo: '3월 11일까지 홈페이지 계정을 만들고 학생 정보를 연동해야 하는 안내입니다.',
    translatedSummary: {
      en: 'This notice asks guardians to create a website account and connect student information by March 11.',
      ar: 'يطلب هذا الإشعار من أولياء الأمور إنشاء حساب في الموقع وربط معلومات الطالب قبل 11 مارس.',
      ru: 'В этом уведомлении родителям нужно создать учетную запись на сайте и привязать данные ученика до 11 марта.',
    },
    refinedBodyKo:
      '가입 대상: 보호자 계정\n' +
      '완료 기한: 2026년 3월 11일\n' +
      '확인 자료: 가입 안내문(HWP), 가입 매뉴얼(PDF)',
    translatedSourceBody: {
      en:
        'Registration target: Guardian account\n' +
        'Completion deadline: March 11, 2026\n' +
        'Reference materials: Registration guide (HWP), registration manual (PDF)',
      ar:
        'الفئة المستهدفة بالتسجيل: حساب ولي الأمر\n' +
        'آخر موعد للإكمال: 11 مارس 2026\n' +
        'المواد المرجعية: دليل التسجيل (HWP)، دليل التسجيل (PDF)',
      ru:
        'Целевая учетная запись: учетная запись родителя\n' +
        'Срок завершения: 11 марта 2026 года\n' +
        'Справочные материалы: инструкция по регистрации (HWP), руководство по регистрации (PDF)',
    },
    dueDate: '2026-03-11',
    eventDates: ['2026-03-11'],
    eventLocation: null,
    crawlResult: {
      source: 'crawl',
      board_url: 'https://www.bcbh.es.kr/board/notice',
      board_kind: 'unknown',
      parser_family: 'school-cms',
      crawl_checked_at: '2026-06-07T09:00:00+09:00',
      post_rank: 5,
      post: {
        title: '2026학년도 부천부흥초 홈페이지 가입 안내',
        published_at: '2026-03-04',
        author: '부천부흥초등학교장',
      },
    },
    attachmentSources: [
      {
        sourceType: 'attachment',
        filename: '2026_홈페이지_가입안내.hwp',
        originUrl: 'https://www.bcbh.es.kr/files/2026-homepage-signup-guide.hwp',
        fixturePath: 'demo-assets/attachments/bucheon-buhung-signup-guide.hwp',
        fileType: 'hwp',
        refinedTextKo: '보호자 계정 생성 절차와 학생명 연동 방법이 안내된 한글 파일입니다.',
        translatedText: {
          en: 'This HWP file explains guardian account creation and student-name linking.',
          ar: 'يشرح ملف HWP هذا إنشاء حساب ولي الأمر وربط اسم الطالب.',
          ru: 'Этот файл HWP объясняет создание учетной записи родителя и привязку имени ученика.',
        },
        needsFile: true,
      },
      {
        sourceType: 'attachment',
        filename: '홈페이지_가입_매뉴얼.pdf',
        originUrl: 'https://www.bcbh.es.kr/files/homepage-registration-manual.pdf',
        fixturePath: 'demo-assets/attachments/bucheon-buhung-registration-manual.pdf',
        fileType: 'pdf',
        refinedTextKo: '로그인 화면, 비밀번호 설정, 학생 정보 연결 순서가 담긴 PDF 매뉴얼입니다.',
        translatedText: {
          en: 'This PDF manual includes the login screen, password setup, and student-linking steps.',
          ar: 'يتضمن دليل PDF هذا شاشة تسجيل الدخول وإعداد كلمة المرور وخطوات ربط الطالب.',
          ru: 'Это PDF-руководство содержит экран входа, настройку пароля и шаги по привязке ученика.',
        },
      },
    ],
    cards: [],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2006',
    sourcePostUid: 'dics-2026-danger-items',
    detailUrl: 'https://www.dics.ms.kr/board/notice/danger-items-2026',
    titleKo: '위험 물품 및 학생 소지 금지 물품 안내',
    translatedTitle: {
      en: 'Notice on Dangerous and Prohibited Student Items',
      ar: 'إشعار بشأن المواد الخطرة والمقتنيات المحظورة على الطلاب',
      ru: 'Уведомление об опасных и запрещенных для учеников предметах',
    },
    originalText:
      '학생 안전을 위해 위험 물품 및 소지 금지 물품을 안내드립니다.\n' +
      '칼, 라이터, 전자담배, 레이저 포인터 등은 학교에 가져오면 안 됩니다.\n' +
      '가정에서 소지품을 함께 점검해 주세요.\n\n2026. 5. 22.\n동인천중학교장',
    translatedBody: {
      en:
        'For student safety, we are sharing the list of dangerous and prohibited items.\n' +
        'Knives, lighters, e-cigarettes, and laser pointers must not be brought to school.\n' +
        'Please check your child’s belongings together at home.',
      ar:
        'من أجل سلامة الطلاب، نشارك قائمة المواد الخطرة والمقتنيات المحظورة.\n' +
        'يُمنع إحضار السكاكين والولاعات والسجائر الإلكترونية وأجهزة الليزر إلى المدرسة.\n' +
        'يُرجى فحص مقتنيات الطفل معًا في المنزل.',
      ru:
        'В целях безопасности учеников мы публикуем список опасных и запрещенных предметов.\n' +
        'Ножи, зажигалки, электронные сигареты и лазерные указки нельзя приносить в школу.\n' +
        'Пожалуйста, проверяйте вещи ребенка дома вместе с ним.',
    },
    summaryKo: '가정에서 학생 소지품을 점검하고 금지 물품을 학교에 가져오지 않도록 안내하는 공지입니다.',
    translatedSummary: {
      en: 'This notice asks families to check student belongings at home and keep prohibited items out of school.',
      ar: 'يطلب هذا الإشعار من العائلات فحص مقتنيات الطلاب في المنزل ومنع إحضار المواد المحظورة إلى المدرسة.',
      ru: 'В этом уведомлении семьям предлагается проверять вещи учеников дома и не приносить запрещенные предметы в школу.',
    },
    refinedBodyKo:
      '금지 물품: 칼, 라이터, 전자담배, 레이저 포인터\n' +
      '가정 협조: 학생 가방과 소지품 사전 점검\n' +
      '첨부 자료: 학생 생활안전 안내 PDF',
    translatedSourceBody: {
      en:
        'Prohibited items: Knives, lighters, e-cigarettes, laser pointers\n' +
        'Family action: Check the student’s bag and belongings in advance\n' +
        'Attachment: Student safety guidance PDF',
      ar:
        'المواد المحظورة: السكاكين، الولاعات، السجائر الإلكترونية، أجهزة الليزر\n' +
        'إجراء الأسرة: فحص حقيبة الطالب ومقتنياته مسبقًا\n' +
        'المرفق: ملف PDF لإرشادات سلامة الطلاب',
      ru:
        'Запрещенные предметы: ножи, зажигалки, электронные сигареты, лазерные указки\n' +
        'Действие семьи: заранее проверьте сумку и вещи ученика\n' +
        'Вложение: PDF-памятка по безопасности учащихся',
    },
    dueDate: null,
    eventDates: [],
    eventLocation: null,
    crawlResult: {
      source: 'crawl',
      board_url: 'https://www.dics.ms.kr/board/notice',
      board_kind: 'unknown',
      parser_family: 'school-cms',
      crawl_checked_at: '2026-06-07T09:00:00+09:00',
      post_rank: 6,
      post: {
        title: '위험 물품 및 학생 소지 금지 물품 안내',
        published_at: '2026-05-22',
        author: '동인천중학교장',
      },
    },
    attachmentSources: [
      {
        sourceType: 'attachment',
        filename: '학생생활안전_안내.pdf',
        originUrl: 'https://www.dics.ms.kr/files/student-safety-guide.pdf',
        fixturePath: 'demo-assets/attachments/dics-student-safety-guide.pdf',
        fileType: 'pdf',
        refinedTextKo: '학생 안전 수칙과 금지 물품 사례가 정리된 PDF 자료입니다.',
        translatedText: {
          en: 'This PDF summarizes student safety rules and examples of prohibited items.',
          ar: 'يلخص ملف PDF هذا قواعد سلامة الطلاب وأمثلة على المواد المحظورة.',
          ru: 'Этот PDF содержит правила безопасности учащихся и примеры запрещенных предметов.',
        },
      },
    ],
    cards: [],
  },
  {
    id: '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d2007',
    sourcePostUid: 'dics-2026-vaccination-grade1',
    detailUrl: 'https://www.dics.ms.kr/board/notice/vaccination-grade1-2026',
    titleKo: '2026학년도 1학년 예방접종 미완료자 접종 안내',
    translatedTitle: {
      en: 'Vaccination Notice for Grade 1 Students with Incomplete Records',
      ar: 'إشعار التطعيم لطلاب الصف الأول ذوي السجلات غير المكتملة',
      ru: 'Уведомление о вакцинации для первоклассников с неполными записями',
    },
    originalText:
      '1학년 예방접종 미완료 학생의 접종 안내입니다.\n' +
      '보호자는 6월 20일까지 예방접종을 완료하고 확인서를 학교로 보내 주세요.\n' +
      '자세한 병원 방문 안내는 첨부 한글 파일을 확인해 주세요.',
    translatedBody: {
      en:
        'This notice is for Grade 1 students whose vaccination records are incomplete.\n' +
        'Guardians should complete the vaccination by June 20 and send the confirmation form to school.\n' +
        'Please review the attached HWP file for detailed clinic-visit guidance.',
      ar:
        'هذا الإشعار مخصص لطلاب الصف الأول الذين لم تكتمل سجلات تطعيمهم.\n' +
        'يُرجى من أولياء الأمور إكمال التطعيم قبل 20 يونيو وإرسال استمارة التأكيد إلى المدرسة.\n' +
        'يُرجى مراجعة ملف HWP المرفق للحصول على إرشادات مفصلة لزيارة العيادة.',
      ru:
        'Это уведомление предназначено для учеников 1 класса с неполными записями о вакцинации.\n' +
        'Родителям нужно завершить вакцинацию до 20 июня и отправить подтверждающую форму в школу.\n' +
        'Пожалуйста, ознакомьтесь с приложенным файлом HWP с подробными инструкциями по посещению клиники.',
    },
    summaryKo: '6월 20일까지 예방접종을 완료하고 확인서를 학교에 제출해야 하는 안내입니다.',
    translatedSummary: {
      en: 'This notice asks families to complete vaccination and submit the confirmation form by June 20.',
      ar: 'يطلب هذا الإشعار من العائلات إكمال التطعيم وتقديم استمارة التأكيد قبل 20 يونيو.',
      ru: 'В этом уведомлении семьям нужно завершить вакцинацию и подать подтверждающую форму до 20 июня.',
    },
    refinedBodyKo:
      '대상: 1학년 예방접종 미완료 학생\n' +
      '완료 기한: 2026년 6월 20일\n' +
      '제출 서류: 예방접종 확인서\n' +
      '첨부 자료: 병원 방문 안내 HWP',
    translatedSourceBody: {
      en:
        'Target: Grade 1 students with incomplete vaccination records\n' +
        'Completion deadline: June 20, 2026\n' +
        'Required document: Vaccination confirmation form\n' +
        'Attachment: HWP clinic-visit guide',
      ar:
        'الفئة المستهدفة: طلاب الصف الأول ذوو سجلات التطعيم غير المكتملة\n' +
        'آخر موعد للإكمال: 20 يونيو 2026\n' +
        'المستند المطلوب: استمارة تأكيد التطعيم\n' +
        'المرفق: دليل زيارة العيادة بصيغة HWP',
      ru:
        'Кому: ученики 1 класса с неполными записями о вакцинации\n' +
        'Срок завершения: 20 июня 2026 года\n' +
        'Необходимый документ: подтверждение о вакцинации\n' +
        'Вложение: инструкция по посещению клиники в формате HWP',
    },
    dueDate: '2026-06-20',
    eventDates: ['2026-06-20'],
    eventLocation: null,
    crawlResult: {
      source: 'crawl',
      board_url: 'https://www.dics.ms.kr/board/notice',
      board_kind: 'unknown',
      parser_family: 'school-cms',
      crawl_checked_at: '2026-06-07T09:00:00+09:00',
      post_rank: 7,
      post: {
        title: '2026학년도 1학년 예방접종 미완료자 접종 안내',
        published_at: '2026-06-03',
        author: '동인천중학교장',
      },
    },
    attachmentSources: [
      {
        sourceType: 'attachment',
        filename: '예방접종_병원방문_안내.hwp',
        originUrl: 'https://www.dics.ms.kr/files/vaccination-clinic-guide.hwp',
        fixturePath: 'demo-assets/attachments/dics-vaccination-clinic-guide.hwp',
        fileType: 'hwp',
        refinedTextKo: '병원 방문 전 준비 사항과 확인서 제출 방법이 담긴 한글 안내문입니다.',
        translatedText: {
          en: 'This HWP guide explains what to prepare before visiting the clinic and how to submit the confirmation form.',
          ar: 'يوضح دليل HWP هذا ما يجب تحضيره قبل زيارة العيادة وكيفية تقديم استمارة التأكيد.',
          ru: 'Это руководство HWP объясняет, что подготовить перед посещением клиники и как подать подтверждение.',
        },
        needsFile: true,
      },
    ],
    cards: [
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4061',
        type: 'action',
        order: 0,
        koItems: [
          { text: '예방접종 완료하기', hint: '2026-06-20' },
          { text: '예방접종 확인서 제출하기', hint: '2026-06-20' },
        ],
        translatedItems: {
          en: [
            { text: 'Complete the vaccination', hint: '2026-06-20' },
            { text: 'Submit the vaccination confirmation form', hint: '2026-06-20' },
          ],
          ar: [
            { text: 'أكمل التطعيم', hint: '2026-06-20' },
            { text: 'قدّم استمارة تأكيد التطعيم', hint: '2026-06-20' },
          ],
          ru: [
            { text: 'Завершите вакцинацию', hint: '2026-06-20' },
            { text: 'Подайте подтверждение о вакцинации', hint: '2026-06-20' },
          ],
        },
      },
      {
        id: '7d27f255-3c41-44fd-8bf4-daa3415a4062',
        type: 'supplies',
        order: 1,
        koItems: [{ text: '예방접종 확인서' }, { text: '병원 방문 안내 HWP' }],
        translatedItems: {
          en: [{ text: 'Vaccination confirmation form' }, { text: 'Clinic-visit guide HWP' }],
          ar: [{ text: 'استمارة تأكيد التطعيم' }, { text: 'دليل زيارة العيادة بصيغة HWP' }],
          ru: [{ text: 'Подтверждение о вакцинации' }, { text: 'Инструкция по посещению клиники HWP' }],
        },
      },
    ],
  },
]

export function isDemoSchoolSelection(input: {
  schoolName?: string | null
  neisOfficeCode?: string | null
  neisSchoolCode?: string | null
}): boolean {
  const officeCode = (input.neisOfficeCode ?? '').trim().toUpperCase()
  const schoolCode = (input.neisSchoolCode ?? '').trim().toUpperCase()
  const schoolName = (input.schoolName ?? '').trim().toLowerCase()
  return (
    (officeCode === DEMO_SCHOOL_OFFICE_CODE && schoolCode === DEMO_SCHOOL_CODE)
    || schoolName === DEMO_SCHOOL_NAME.toLowerCase()
  )
}

export function maybeInjectDemoSchoolResult<T extends {
  name: string
  level: string
  officeCode: string
  schoolCode: string
  address: string
  homepageUrl?: string
}>(query: string, results: T[]): T[] {
  const normalized = query.trim().toLowerCase().replace(/\s+/g, '')
  const shouldInclude = normalized.includes('naranhi') || normalized.includes('demo') || normalized.includes('나란히')
  if (!shouldInclude) return results
  const alreadyExists = results.some(
    school =>
      school.officeCode === DEMO_SCHOOL_OFFICE_CODE
      && school.schoolCode === DEMO_SCHOOL_CODE,
  )
  if (alreadyExists) return results
  return [DEMO_SCHOOL_SEARCH_RESULT as T, ...results]
}

function stableDemoUuid(seed: string): string {
  const hex = createHash('sha1').update(seed).digest('hex').slice(0, 32)
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`
}

function isStaticDemoNoticeSeed(seed: DemoNoticeSeed): boolean {
  return seed.detailUrl.startsWith('demo://')
}

function jsonRecord(value: Json | null | undefined): Record<string, Json> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, Json> : {}
}

function jsonArray(value: Json | null | undefined): Json[] {
  return Array.isArray(value) ? value : []
}

function hasStorageAttachment(extractedContent: Json | null): boolean {
  const extracted = jsonRecord(extractedContent)
  const sources = jsonArray(extracted.sources)
  return sources.some(source => {
    const sourceObj = jsonRecord(source)
    const role = typeof sourceObj.source_role === 'string' ? sourceObj.source_role : ''
    const sourceType = typeof sourceObj.source_type === 'string' ? sourceObj.source_type : ''
    const filename = typeof sourceObj.filename === 'string' ? sourceObj.filename.trim() : ''
    const publicUrl = typeof sourceObj.public_url === 'string' ? sourceObj.public_url.trim() : ''
    return (
      Boolean(publicUrl)
      && (
        role === 'attachment'
        || role === 'primary'
        || sourceType.startsWith('attachment_')
        || Boolean(filename)
      )
    )
  })
}

async function getDemoNoticeDonorSchoolId(serviceClient: ServiceClient): Promise<string | null> {
  for (const schoolName of DEMO_NOTICE_DONOR_SCHOOL_NAMES) {
    const { data: school } = await serviceClient
      .from('schools')
      .select('id')
      .eq('name', schoolName)
      .maybeSingle()

    if (typeof school?.id === 'string' && school.id) {
      return school.id
    }
  }

  return null
}

interface ReusedNoticeSeedBundle {
  notices: Array<Database['public']['Tables']['notices']['Insert']>
  translations: Array<Database['public']['Tables']['notice_ai_translations']['Insert']>
  cards: Array<Database['public']['Tables']['notice_cards']['Insert']>
  cardTranslations: Array<Database['public']['Tables']['notice_card_translations']['Insert']>
  events: Array<Database['public']['Tables']['school_events']['Insert']>
}

async function buildReusedDemoNotices(
  serviceClient: ServiceClient,
  schoolId: string,
): Promise<ReusedNoticeSeedBundle> {
  const donorSchoolId = await getDemoNoticeDonorSchoolId(serviceClient)
  if (!donorSchoolId) {
    return { notices: [], translations: [], cards: [], cardTranslations: [], events: [] }
  }

  const { data: candidateNotices } = await serviceClient
    .from('notices')
    .select(
      'id, school_id, status, title, original_text, source_post_uid, detail_url, crawl_result, extracted_content, error_message, due_date, event_dates, event_location, source_hard_facts, extraction_attempts, extraction_started_at, extraction_next_run_at, extraction_error_code, created_at, updated_at',
    )
    .eq('school_id', donorSchoolId)
    .eq('status', 'done')
    .order('created_at', { ascending: false })
    .limit(12)

  const sourceNotices = (candidateNotices ?? [])
    .filter(notice => hasStorageAttachment(notice.extracted_content))
    .slice(0, DEMO_NOTICE_REUSE_LIMIT)

  if (sourceNotices.length === 0) {
    return { notices: [], translations: [], cards: [], cardTranslations: [], events: [] }
  }

  const sourceNoticeIds = sourceNotices.map(notice => notice.id)

  const [{ data: translationRows }, { data: cardRows }, { data: eventRows }] = await Promise.all([
    serviceClient
      .from('notice_ai_translations')
      .select('notice_id,target_language,source_language,translated_title,translated_location,translated_text,validation_status,updated_at')
      .in('notice_id', sourceNoticeIds),
    serviceClient
      .from('notice_cards')
      .select('id,notice_id,type,order,content')
      .in('notice_id', sourceNoticeIds),
    serviceClient
      .from('school_events')
      .select('notice_id,title,event_date,event_kinds,location,description,source_language')
      .in('notice_id', sourceNoticeIds),
  ])

  const sourceCards = cardRows ?? []
  const sourceCardIds = sourceCards.map(card => card.id)
  const { data: cardTranslationRows } = sourceCardIds.length > 0
    ? await serviceClient
        .from('notice_card_translations')
        .select('notice_card_id,target_language,translated_content,updated_at')
        .in('notice_card_id', sourceCardIds)
    : { data: [] as NoticeCardTranslationRow[] }

  const noticeIdMap = new Map(sourceNotices.map(notice => [notice.id, stableDemoUuid(`demo-notice:${notice.id}`)]))
  const cardIdMap = new Map(sourceCards.map(card => [card.id, stableDemoUuid(`demo-card:${card.id}`)]))

  const notices = sourceNotices.map(notice => ({
    id: noticeIdMap.get(notice.id)!,
    school_id: schoolId,
    title: notice.title,
    original_text: notice.original_text,
    source_post_uid: notice.source_post_uid ? `demo-${notice.source_post_uid}` : null,
    detail_url: notice.detail_url,
    crawl_result: {
      ...jsonRecord(notice.crawl_result),
      source: 'demo_reused',
      demo_source_school_id: donorSchoolId,
      demo_source_notice_id: notice.id,
    } satisfies Json,
    extracted_content: notice.extracted_content,
    status: notice.status,
    error_message: notice.error_message,
    due_date: notice.due_date,
    event_dates: notice.event_dates,
    event_location: notice.event_location,
    source_hard_facts: notice.source_hard_facts,
    extraction_attempts: notice.extraction_attempts,
    extraction_started_at: notice.extraction_started_at,
    extraction_next_run_at: notice.extraction_next_run_at,
    extraction_error_code: notice.extraction_error_code,
    created_at: notice.created_at,
    updated_at: notice.updated_at,
  }))

  const translations = (translationRows ?? []).flatMap(row => {
    const mappedNoticeId = noticeIdMap.get(row.notice_id)
    if (!mappedNoticeId) return []
    return [{
      notice_id: mappedNoticeId,
      target_language: row.target_language,
      source_language: row.source_language,
      translated_title: row.translated_title,
      translated_location: row.translated_location,
      translated_text: row.translated_text,
      validation_status: row.validation_status,
      updated_at: row.updated_at,
    }]
  })

  const cards = sourceCards.flatMap(card => {
    const mappedNoticeId = noticeIdMap.get(card.notice_id)
    const mappedCardId = cardIdMap.get(card.id)
    if (!mappedNoticeId || !mappedCardId) return []
    return [{
      id: mappedCardId,
      notice_id: mappedNoticeId,
      type: card.type,
      order: card.order,
      content: card.content,
    }]
  })

  const cardTranslations = (cardTranslationRows ?? []).flatMap(row => {
    const mappedCardId = cardIdMap.get(row.notice_card_id)
    if (!mappedCardId) return []
    return [{
      notice_card_id: mappedCardId,
      target_language: row.target_language,
      translated_content: row.translated_content,
      updated_at: row.updated_at,
    }]
  })

  const events = (eventRows ?? []).flatMap(event => {
    const mappedNoticeId = noticeIdMap.get(event.notice_id)
    if (!mappedNoticeId) return []
    return [{
      school_id: schoolId,
      notice_id: mappedNoticeId,
      title: event.title,
      event_date: event.event_date,
      event_kinds: event.event_kinds,
      location: event.location,
      description: event.description,
      source_language: event.source_language,
    }]
  })

  return { notices, translations, cards, cardTranslations, events }
}

export async function ensureDemoSchoolSeed(
  serviceClient: ServiceClient,
  schoolId: string,
): Promise<void> {
  const reusedNotices = await buildReusedDemoNotices(serviceClient, schoolId)

  await serviceClient
    .from('schools')
    .update({
      name: DEMO_SCHOOL_NAME,
      address: DEMO_SCHOOL_ADDRESS,
      homepage_url: DEMO_SCHOOL_HOMEPAGE_URL,
      neis_office_code: DEMO_SCHOOL_OFFICE_CODE,
      neis_school_code: DEMO_SCHOOL_CODE,
    })
    .eq('id', schoolId)

  await serviceClient
    .from('school_crawl_state')
    .upsert(
      {
        school_id: schoolId,
        crawl_board_url: 'demo://naranhi-school/board',
        crawl_board_kind: 'unknown',
        crawl_status: 'completed',
        crawl_error_message: null,
        crawl_result: {
          source: 'demo_reused',
          seeded_notice_count: reusedNotices.notices.length,
        } satisfies Json,
        crawl_last_checked_at: new Date().toISOString(),
      },
      { onConflict: 'school_id' },
    )

  const reusedNoticeIds = reusedNotices.notices
    .map(notice => notice.id)
    .filter((noticeId): noticeId is string => typeof noticeId === 'string' && noticeId.length > 0)

  const { data: existingDemoNotices } = await serviceClient
    .from('notices')
    .select('id,detail_url,crawl_result')
    .eq('school_id', schoolId)

  const staleDemoNoticeIds = (existingDemoNotices ?? [])
    .filter(notice => {
      if (reusedNoticeIds.includes(notice.id)) return false
      const detailUrl = typeof notice.detail_url === 'string' ? notice.detail_url : ''
      const crawlResult = jsonRecord(notice.crawl_result)
      const source = typeof crawlResult.source === 'string' ? crawlResult.source : ''
      return detailUrl.startsWith('demo://') || source === 'demo' || source === 'demo_reused'
    })
    .map(notice => notice.id)

  if (staleDemoNoticeIds.length > 0) {
    await serviceClient
      .from('notices')
      .delete()
      .in('id', staleDemoNoticeIds)
  }

  if (reusedNotices.notices.length > 0) {
    await serviceClient
      .from('notices')
      .upsert(reusedNotices.notices, { onConflict: 'id' })
  }

  if (reusedNotices.translations.length > 0) {
    await serviceClient
      .from('notice_ai_translations')
      .upsert(reusedNotices.translations, { onConflict: 'notice_id,target_language' })
  }

  if (reusedNoticeIds.length > 0) {
    await serviceClient
      .from('notice_cards')
      .delete()
      .in('notice_id', reusedNoticeIds)
  }

  if (reusedNotices.cards.length > 0) {
    await serviceClient
      .from('notice_cards')
      .upsert(reusedNotices.cards, { onConflict: 'id' })
  }

  if (reusedNotices.cardTranslations.length > 0) {
    await serviceClient
      .from('notice_card_translations')
      .upsert(reusedNotices.cardTranslations, { onConflict: 'notice_card_id,target_language' })
  }

  await serviceClient
    .from('school_events')
    .upsert(reusedNotices.events, { onConflict: 'notice_id,event_date' })

  await seedDemoMeals(serviceClient)
}

function buildDemoEventEntries(
  eventDates: string[],
  dueDate: string | null,
): Array<{ eventDate: string; eventKinds: ('event' | 'deadline')[] }> {
  const rows = eventDates.map(eventDate => ({
    eventDate,
    eventKinds: [eventDate === dueDate ? 'deadline' : 'event'] as ('event' | 'deadline')[],
  }))
  if (dueDate && !eventDates.includes(dueDate)) {
    rows.push({ eventDate: dueDate, eventKinds: ['deadline'] })
  }
  return rows
}

export async function getDemoMealSourceCodes(
  serviceClient: ServiceClient,
): Promise<{ officeCode: string; schoolCode: string } | null> {
  for (const schoolName of DEMO_MEAL_DONOR_SCHOOL_NAMES) {
    const { data: school } = await serviceClient
      .from('schools')
      .select('neis_office_code,neis_school_code')
      .eq('name', schoolName)
      .maybeSingle()

    const officeCode = typeof school?.neis_office_code === 'string' ? school.neis_office_code.trim() : ''
    const schoolCode = typeof school?.neis_school_code === 'string' ? school.neis_school_code.trim() : ''
    if (officeCode && schoolCode) {
      return { officeCode, schoolCode }
    }
  }

  const { data } = await serviceClient
    .from('meals')
    .select('office_code,school_code')
    .order('fetched_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  const officeCode = typeof data?.office_code === 'string' ? data.office_code.trim() : ''
  const schoolCode = typeof data?.school_code === 'string' ? data.school_code.trim() : ''
  if (!officeCode || !schoolCode) {
    return null
  }
  return { officeCode, schoolCode }
}

function todayKstIso(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function addDaysIso(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const base = Date.UTC(year, month - 1, day)
  const next = new Date(base + days * 86400000)
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}-${String(next.getUTCDate()).padStart(2, '0')}`
}

async function seedDemoMeals(serviceClient: ServiceClient): Promise<void> {
  const donor = await getDemoMealSourceCodes(serviceClient)
  if (!donor) return

  if (
    donor.officeCode === DEMO_SCHOOL_OFFICE_CODE
    && donor.schoolCode === DEMO_SCHOOL_CODE
  ) {
    return
  }

  const today = todayKstIso()
  const fromIso = addDaysIso(today, -DEMO_MEAL_SEED_WINDOW_DAYS)
  const toIso = addDaysIso(today, DEMO_MEAL_SEED_WINDOW_DAYS)

  const { data: donorMeals, error } = await serviceClient
    .from('meals')
    .select('meal_date,meal_type,meal_type_name,dishes,calories,nutrients,origins')
    .eq('office_code', donor.officeCode)
    .eq('school_code', donor.schoolCode)
    .gte('meal_date', fromIso)
    .lte('meal_date', toIso)
    .order('meal_date', { ascending: true })
    .order('meal_type', { ascending: true })

  if (error || !donorMeals || donorMeals.length === 0) {
    return
  }

  await serviceClient
    .from('meals')
    .upsert(
      donorMeals.map(meal => ({
        office_code: DEMO_SCHOOL_OFFICE_CODE,
        school_code: DEMO_SCHOOL_CODE,
        meal_date: meal.meal_date,
        meal_type: meal.meal_type,
        meal_type_name: meal.meal_type_name,
        dishes: meal.dishes,
        calories: meal.calories,
        nutrients: meal.nutrients,
        origins: meal.origins,
      })),
      { onConflict: 'office_code,school_code,meal_date,meal_type' },
    )
}

export async function getSeededDemoMealsForRange(
  serviceClient: ServiceClient,
  fromIso: string,
  toIso: string,
): Promise<Map<string, Database['public']['Tables']['meals']['Row'][]>> {
  const { data } = await serviceClient
    .from('meals')
    .select('*')
    .eq('office_code', DEMO_SCHOOL_OFFICE_CODE)
    .eq('school_code', DEMO_SCHOOL_CODE)
    .gte('meal_date', fromIso)
    .lte('meal_date', toIso)
    .order('meal_date', { ascending: true })
    .order('meal_type', { ascending: true })

  const map = new Map<string, Database['public']['Tables']['meals']['Row'][]>()
  for (const meal of data ?? []) {
    const bucket = map.get(meal.meal_date) ?? []
    bucket.push(meal)
    map.set(meal.meal_date, bucket)
  }
  return map
}
