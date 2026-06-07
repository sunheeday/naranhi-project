import 'server-only'

import type { SupabaseClient } from '@supabase/supabase-js'
import type { Database, Json } from '@/types/database'

export const DEMO_SCHOOL_NAME = 'Naranhi School'
export const DEMO_SCHOOL_LEVEL = 'Demo'
export const DEMO_SCHOOL_ADDRESS = 'Seoul Demo Campus, 101 Story Lane'
export const DEMO_SCHOOL_OFFICE_CODE = 'DEMO'
export const DEMO_SCHOOL_CODE = 'NARANHI001'
export const DEMO_SCHOOL_HOMEPAGE_URL = 'https://demo.naranhi.school'

type ServiceClient = SupabaseClient<Database>

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

export async function ensureDemoSchoolSeed(
  serviceClient: ServiceClient,
  schoolId: string,
): Promise<void> {
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
          source: 'demo',
          seeded_notice_count: DEMO_NOTICE_SEEDS.length,
        } satisfies Json,
        crawl_last_checked_at: new Date().toISOString(),
      },
      { onConflict: 'school_id' },
    )

  const noticeRows = DEMO_NOTICE_SEEDS.map((seed, index) => ({
    id: seed.id,
    school_id: schoolId,
    title: seed.titleKo,
    original_text: seed.originalText,
    source_post_uid: null,
    detail_url: seed.detailUrl,
    crawl_result: {
      source: 'demo',
      crawl_checked_at: '2026-06-07T09:00:00+09:00',
      post_rank: index + 1,
    } satisfies Json,
    extracted_content: {
      summary: {
        rendered: seed.summaryKo,
        translations: seed.translatedSummary,
      },
      sources: [
        {
          source_type: 'html_body',
          refined_text: seed.refinedBodyKo,
          translations: seed.translatedSourceBody,
          needs_file: false,
          metadata: { order_index: 0 },
        },
      ],
      needs_file: false,
    } satisfies Json,
    status: 'done' as const,
    error_message: null,
    due_date: seed.dueDate,
    event_dates: seed.eventDates,
    event_location: seed.eventLocation,
    source_hard_facts: {
      hard_facts: {
        dates: seed.eventDates.map(date => ({ raw_text: date, normalized: date })),
        deadlines: seed.dueDate ? [{ raw_text: seed.dueDate, normalized: seed.dueDate }] : [],
      },
    } satisfies Json,
    extraction_attempts: 1,
    extraction_started_at: '2026-06-07T09:00:00+09:00',
    extraction_next_run_at: null,
    extraction_error_code: null,
    created_at: `2026-06-07T0${Math.min(index + 7, 9)}:00:00+09:00`,
    updated_at: `2026-06-07T0${Math.min(index + 7, 9)}:00:00+09:00`,
  }))

  await serviceClient
    .from('notices')
    .upsert(noticeRows, { onConflict: 'id' })

  const noticeTranslations = DEMO_NOTICE_SEEDS.flatMap(seed =>
    DEMO_LANGUAGES.map(language => ({
      notice_id: seed.id,
      target_language: language,
      source_language: 'ko',
      translated_text: `${seed.translatedTitle[language]}\n\n${seed.translatedBody[language]}`,
      validation_status: 'passed' as const,
    })),
  )

  await serviceClient
    .from('notice_ai_translations')
    .upsert(noticeTranslations, { onConflict: 'notice_id,target_language' })

  const cardRows = DEMO_NOTICE_SEEDS.flatMap(seed =>
    seed.cards.map(card => ({
      id: card.id,
      notice_id: seed.id,
      type: card.type,
      order: card.order,
      content: {
        ko: {
          items: card.koItems,
        },
      } satisfies Json,
    })),
  )

  await serviceClient
    .from('notice_cards')
    .upsert(cardRows, { onConflict: 'id' })

  const cardTranslations = DEMO_NOTICE_SEEDS.flatMap(seed =>
    seed.cards.flatMap(card =>
      DEMO_LANGUAGES.map(language => ({
        notice_card_id: card.id,
        target_language: language,
        translated_content: {
          items: card.translatedItems[language],
        } satisfies Json,
      })),
    ),
  )

  await serviceClient
    .from('notice_card_translations')
    .upsert(cardTranslations, { onConflict: 'notice_card_id,target_language' })

  const schoolEvents = DEMO_NOTICE_SEEDS.flatMap(seed =>
    seed.eventDates.map(eventDate => ({
      school_id: schoolId,
      notice_id: seed.id,
      title: seed.titleKo,
      event_date: eventDate,
      location: seed.eventLocation,
      description: seed.summaryKo,
      source_language: 'ko',
    })),
  )

  await serviceClient
    .from('school_events')
    .upsert(schoolEvents, { onConflict: 'notice_id,event_date' })
}

export async function getDemoMealSourceCodes(
  serviceClient: ServiceClient,
): Promise<{ officeCode: string; schoolCode: string } | null> {
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
