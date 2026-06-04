#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const { createClient } = require('@supabase/supabase-js')

const repoRoot = path.resolve(__dirname, '..')
loadEnvFile(path.join(repoRoot, '.env.local'))

const supabaseUrl = mustGetEnv('NEXT_PUBLIC_SUPABASE_URL')
const serviceRoleKey = mustGetEnv('SUPABASE_SERVICE_ROLE_KEY')

const demoEmail = process.env.ARABIC_DEMO_EMAIL || process.env.DEV_LOGIN_EMAIL || 'demo.ar.parent@naranhi.local'
const demoPassword = process.env.ARABIC_DEMO_PASSWORD || process.env.DEV_LOGIN_PASSWORD || 'NaranhiArabicDemo2026!'

const supabase = createClient(supabaseUrl, serviceRoleKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
})

const SCHOOL_CODES = {
  office: 'J10',
  school: '7611063',
}

const CHILD = {
  name: 'ليلى',
  schoolName: '안산원곡초등학교',
  grade: 2,
  classNo: 3,
}

const MEAL_WEEK = {
  from: '2026-06-01',
  to: '2026-06-05',
}

const NOTICE = {
  sourcePostUid: 'demo-ar-field-trip-2026-10-19',
  titleKo: '2학년 현장체험학습 참가 동의서 안내',
  titleAr: 'إشعار موافقة المشاركة في الرحلة الميدانية للصف الثاني',
  originalText: `# 2학년 현장체험학습 참가 동의서 안내

학부모님께,

2026학년도 2학년 현장체험학습을 아래와 같이 실시하고자 합니다. 참가를 희망하는 경우 동의서를 작성하여 제출해 주시기 바랍니다.

- 일시: 2026년 10월 19일(월) 08:20 ~ 2026년 10월 21일(수) 16:30
- 장소: 국립해양생태수련원
- 대상: 2학년 전체 학생
- 참가비: 71,600원
- 납부 기한: 2026년 9월 18일(금) 17:00까지
- 납부 방법: 학교 CMS 자동이체
- 준비물: 세면도구, 운동화, 여벌 옷, 개인 상비약
- 제출물: 참가 동의서 1부
- 동의서 제출 마감: 2026년 9월 11일(금)

불참을 희망하는 경우에도 사유를 적어 반드시 회신해 주시기 바랍니다.

문의: 2학년부 031-880-2214
`,
  translatedText: `# إشعار موافقة المشاركة في الرحلة الميدانية للصف الثاني

أولياء الأمور الكرام،

نود تنفيذ الرحلة الميدانية لطلاب الصف الثاني للعام الدراسي 2026 وفق التفاصيل الآتية. يرجى تعبئة استمارة الموافقة وإرسالها إذا رغبتم في مشاركة الطالب/ـة.

- الموعد: 2026-10-19 (الاثنين) 08:20 حتى 2026-10-21 (الأربعاء) 16:30
- المكان: المركز الوطني للتدريب البيئي البحري
- الفئة المستهدفة: جميع طلاب الصف الثاني
- رسوم المشاركة: 71,600 وون
- آخر موعد للدفع: 2026-09-18 (الجمعة) الساعة 17:00
- طريقة الدفع: خصم آلي عبر نظام CMS المدرسي
- المستلزمات: أدوات نظافة شخصية، حذاء رياضي، ملابس إضافية، أدوية شخصية عند الحاجة
- المستند المطلوب: استمارة موافقة واحدة
- آخر موعد لتسليم الاستمارة: 2026-09-11 (الجمعة)

إذا كنتم لا ترغبون في المشاركة، فيرجى أيضاً إرسال الرد مع توضيح السبب.

للاستفسار: قسم الصف الثاني 031-880-2214
`,
}

const CARD_CONTENT = [
  {
    type: 'action',
    order: 1,
    content: {
      ko: {
        items: [
          {
            text: '참가 동의서 제출',
            hint: '2026년 9월 11일(금)까지 담임교사에게 제출',
          },
          {
            text: '참가비 71,600원 납부',
            hint: '2026년 9월 18일(금) 17:00까지 학교 CMS 자동이체',
          },
        ],
      },
      ar: {
        items: [
          {
            text: 'تسليم استمارة الموافقة',
            hint: 'يرجى تسليمها إلى المعلم/ـة حتى 2026-09-11 (الجمعة)',
          },
          {
            text: 'دفع رسوم المشاركة 71,600 وون',
            hint: 'حتى 2026-09-18 (الجمعة) 17:00 عبر خصم CMS المدرسي',
          },
        ],
      },
    },
  },
  {
    type: 'schedule',
    order: 2,
    content: {
      ko: {
        items: [
          {
            text: '현장체험학습 일정',
            hint: '2026년 10월 19일(월) 08:20 출발 ~ 10월 21일(수) 16:30 종료',
          },
          {
            text: '장소',
            hint: '국립해양생태수련원',
          },
        ],
      },
      ar: {
        items: [
          {
            text: 'جدول الرحلة الميدانية',
            hint: 'من 2026-10-19 (الاثنين) 08:20 إلى 2026-10-21 (الأربعاء) 16:30',
          },
          {
            text: 'المكان',
            hint: 'المركز الوطني للتدريب البيئي البحري',
          },
        ],
      },
    },
  },
  {
    type: 'supplies',
    order: 3,
    content: {
      ko: {
        items: [
          {
            text: '세면도구',
          },
          {
            text: '운동화',
          },
          {
            text: '여벌 옷',
          },
          {
            text: '개인 상비약',
            hint: '필요한 학생만 준비',
          },
        ],
      },
      ar: {
        items: [
          {
            text: 'أدوات نظافة شخصية',
          },
          {
            text: 'حذاء رياضي',
          },
          {
            text: 'ملابس إضافية',
          },
          {
            text: 'أدوية شخصية',
            hint: 'للطلبة الذين يحتاجون إليها فقط',
          },
        ],
      },
    },
  },
]

async function main() {
  const user = await ensureAuthUser()
  await upsertProfile(user)
  const school = await upsertSchool()
  const child = await createChild(user.id, school.id)
  const mealSummary = await warmMealsCache()
  const notice = await upsertNotice(user.id, school.id)
  await upsertTranslation(notice.id)
  await replaceCards(notice.id)
  await replaceSchedule(notice.id, child.id)

  console.log(JSON.stringify({
    ok: true,
    email: demoEmail,
    devLoginEnabled: true,
    locale: 'ar',
    schoolId: school.id,
    childId: child.id,
    mealsWeek: MEAL_WEEK,
    mealsCachedDays: mealSummary.days,
    mealsCachedRows: mealSummary.rows,
    noticeId: notice.id,
    noticeTitle: NOTICE.titleAr,
  }, null, 2))
}

async function ensureAuthUser() {
  const { data, error } = await supabase.auth.admin.listUsers({ page: 1, perPage: 200 })
  if (error) {
    throw error
  }

  const existing = (data.users || []).find(user => user.email === demoEmail)
  if (existing) {
    const { data: updated, error: updateError } = await supabase.auth.admin.updateUserById(existing.id, {
      email: demoEmail,
      password: demoPassword,
      email_confirm: true,
      user_metadata: {
        full_name: 'Arabic Demo Parent',
      },
    })
    if (updateError) {
      throw updateError
    }
    return updated.user
  }

  const { data: created, error: createError } = await supabase.auth.admin.createUser({
    email: demoEmail,
    password: demoPassword,
    email_confirm: true,
    user_metadata: {
      full_name: 'Arabic Demo Parent',
    },
  })
  if (createError) {
    throw createError
  }
  return created.user
}

async function upsertProfile(user) {
  const { error } = await supabase
    .from('profiles')
    .upsert({
      id: user.id,
      email: demoEmail,
      display_name: 'Arabic Demo Parent',
      locale: 'ar',
      native_language: 'ar',
      role: 'parent',
    }, { onConflict: 'id' })

  if (error) {
    throw error
  }
}

async function upsertSchool() {
  const payload = {
    name: CHILD.schoolName,
    neis_office_code: SCHOOL_CODES.office,
    neis_school_code: SCHOOL_CODES.school,
    address: '경기도 안산시 단원구 원곡초교길 9',
    homepage_url: 'https://ansanwongok-e.goeas.kr',
    crawl_board_url: 'https://ansanwongok-e.goeas.kr/ansanwongok-e/main.do',
    crawl_board_kind: 'family_notice',
    crawl_status: 'success',
    crawl_error_message: null,
    crawl_result: {
      seeded_by: 'scripts/seed-arabic-demo-account.cjs',
      demo: true,
      uses_real_neis_school: true,
    },
    crawl_last_checked_at: new Date().toISOString(),
  }

  const { data, error } = await supabase
    .from('schools')
    .upsert(payload, { onConflict: 'neis_office_code,neis_school_code' })
    .select('id, name')
    .single()

  if (error) {
    throw error
  }
  return data
}

async function createChild(userId, schoolId) {
  const { error: cleanupError } = await supabase
    .from('children')
    .delete()
    .eq('user_id', userId)

  if (cleanupError) {
    throw cleanupError
  }

  const { data, error } = await supabase
    .from('children')
    .insert({
      user_id: userId,
      school_id: schoolId,
      name: CHILD.name,
      school_name: CHILD.schoolName,
      grade: CHILD.grade,
      class_no: CHILD.classNo,
      neis_office_code: SCHOOL_CODES.office,
      neis_school_code: SCHOOL_CODES.school,
    })
    .select('id, name')
    .single()

  if (error) {
    throw error
  }
  return data
}

async function warmMealsCache() {
  const rows = await fetchMealsRangeFromNeis(
    SCHOOL_CODES.office,
    SCHOOL_CODES.school,
    MEAL_WEEK.from.replace(/-/g, ''),
    MEAL_WEEK.to.replace(/-/g, ''),
  )

  if (rows.length === 0) {
    return { days: 0, rows: 0 }
  }

  const payload = rows.map(meal => ({
    office_code: SCHOOL_CODES.office,
    school_code: SCHOOL_CODES.school,
    meal_date: meal.date,
    meal_type: meal.mealType,
    meal_type_name: meal.mealTypeName,
    dishes: meal.dishes,
    calories: meal.calories,
    nutrients: meal.nutrients,
    origins: meal.origins,
  }))

  const { error } = await supabase
    .from('meals')
    .upsert(payload, { onConflict: 'office_code,school_code,meal_date,meal_type' })

  if (error) {
    throw error
  }

  const uniqueDays = new Set(rows.map(row => row.date))
  return { days: uniqueDays.size, rows: rows.length }
}

async function upsertNotice(userId, schoolId) {
  const { data: existing, error: existingError } = await supabase
    .from('notices')
    .select('id')
    .eq('school_id', schoolId)
    .eq('source_post_uid', NOTICE.sourcePostUid)
    .maybeSingle()

  if (existingError) {
    throw existingError
  }

  const payload = {
    school_id: schoolId,
    title: NOTICE.titleKo,
    original_text: NOTICE.originalText,
    source_post_uid: NOTICE.sourcePostUid,
    detail_url: 'https://demo-school.naranhi.local/family-notices/field-trip-2026',
    crawl_result: {
      seeded_by: 'scripts/seed-arabic-demo-account.cjs',
      demo: true,
      locale_ready: 'ar',
    },
    extracted_content: {
      seeded: true,
      summaries: {
        ko: NOTICE.titleKo,
        ar: NOTICE.titleAr,
      },
    },
    status: 'done',
    error_message: null,
    extraction_attempts: 1,
    extraction_started_at: new Date().toISOString(),
    extraction_next_run_at: null,
    extraction_error_code: null,
  }

  if (existing) {
    const { data, error } = await supabase
      .from('notices')
      .update(payload)
      .eq('id', existing.id)
      .select('id')
      .single()

    if (error) {
      throw error
    }
    return data
  }

  const { data, error } = await supabase
    .from('notices')
    .insert(payload)
    .select('id')
    .single()

  if (error) {
    throw error
  }
  return data
}

async function upsertTranslation(noticeId) {
  const metadata = {
    summary_ko: NOTICE.titleKo,
    summary_target_language: NOTICE.titleAr,
    target_language: 'ar',
    seeded_by: 'scripts/seed-arabic-demo-account.cjs',
  }

  const { error } = await supabase
    .from('notice_ai_translations')
    .upsert({
      notice_id: noticeId,
      target_language: 'ar',
      source_language: 'ko',
      source_text: NOTICE.originalText,
      translated_text: NOTICE.translatedText,
      source_hard_facts: {},
      target_hard_facts: {},
      ingredient_identity_map: {},
      validation: {
        status: 'seeded_demo',
      },
      metadata,
      raw_pipeline: {
        seeded_demo: true,
      },
      validation_status: 'passed',
      requires_admin_review: false,
      admin_review_reason: null,
    }, { onConflict: 'notice_id,target_language' })

  if (error) {
    throw error
  }
}

async function replaceCards(noticeId) {
  const { error: deleteError } = await supabase
    .from('notice_cards')
    .delete()
    .eq('notice_id', noticeId)

  if (deleteError) {
    throw deleteError
  }

  const rows = CARD_CONTENT.map(card => ({
    notice_id: noticeId,
    type: card.type,
    order: card.order,
    content: card.content,
  }))

  const { error } = await supabase
    .from('notice_cards')
    .insert(rows)

  if (error) {
    throw error
  }
}

async function replaceSchedule(noticeId, childId) {
  const { error: deleteError } = await supabase
    .from('schedules')
    .delete()
    .eq('notice_id', noticeId)
    .eq('child_id', childId)

  if (deleteError) {
    throw deleteError
  }

  const { error } = await supabase
    .from('schedules')
    .insert({
      notice_id: noticeId,
      child_id: childId,
      title: 'الرحلة الميدانية للصف الثاني',
      event_date: '2026-10-19',
      location: 'المركز الوطني للتدريب البيئي البحري',
      description: 'موعد الرحلة الميدانية الرئيسي للصف الثاني.',
    })

  if (error) {
    throw error
  }
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return
  }

  const source = fs.readFileSync(filePath, 'utf8')
  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) {
      continue
    }
    const separatorIndex = line.indexOf('=')
    if (separatorIndex <= 0) {
      continue
    }
    const key = line.slice(0, separatorIndex).trim()
    const value = line.slice(separatorIndex + 1)
    if (!(key in process.env)) {
      process.env[key] = value
    }
  }
}

function mustGetEnv(name) {
  const value = process.env[name]
  if (!value) {
    throw new Error(`Missing required env: ${name}`)
  }
  return value
}

function getNeisApiKey() {
  return mustGetEnv('NEIS_API_KEY')
}

async function fetchMealsRangeFromNeis(officeCode, schoolCode, fromYmd, toYmd) {
  const url = new URL('https://open.neis.go.kr/hub/mealServiceDietInfo')
  url.searchParams.set('KEY', getNeisApiKey())
  url.searchParams.set('Type', 'json')
  url.searchParams.set('pIndex', '1')
  url.searchParams.set('pSize', '100')
  url.searchParams.set('ATPT_OFCDC_SC_CODE', officeCode)
  url.searchParams.set('SD_SCHUL_CODE', schoolCode)
  url.searchParams.set('MLSV_FROM_YMD', fromYmd)
  url.searchParams.set('MLSV_TO_YMD', toYmd)

  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`NEIS mealServiceDietInfo ${response.status}`)
  }

  const body = await response.json()
  const rows = extractRows(body, 'mealServiceDietInfo')
  return rows.map(row => ({
    mealType: Number(row.MMEAL_SC_CODE),
    mealTypeName: row.MMEAL_SC_NM,
    dishes: parseDishes(row.DDISH_NM ?? ''),
    calories: row.CAL_INFO ?? null,
    nutrients: parseBrLines(row.NTR_INFO),
    origins: parseOrigins(row.ORPLC_INFO),
    date: `${row.MLSV_YMD.slice(0, 4)}-${row.MLSV_YMD.slice(4, 6)}-${row.MLSV_YMD.slice(6, 8)}`,
  }))
}

function extractRows(envelope, key) {
  const blocks = envelope?.[key]
  if (!Array.isArray(blocks)) {
    return []
  }
  for (const block of blocks) {
    if (block && Array.isArray(block.row)) {
      return block.row
    }
  }
  return []
}

function parseDishes(ddish) {
  return String(ddish)
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const cleaned = line.replace(/^\*+/, '').trim()
      const matched = cleaned.match(/^(.+?)\s*\(?([\d.]+)\)?\s*$/)
      if (matched && matched[2].includes('.')) {
        return {
          name: matched[1].trim(),
          allergens: matched[2].split('.').map(Number).filter(Number.isFinite),
        }
      }
      const starParts = cleaned.split('*')
      if (starParts.length === 2) {
        return {
          name: starParts[0].trim(),
          allergens: starParts[1].split('.').map(Number).filter(Number.isFinite),
        }
      }
      return {
        name: cleaned,
        allergens: [],
      }
    })
}

function parseBrLines(value) {
  if (!value) {
    return null
  }
  return String(value)
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const matched = line.match(/^(.+?)\s*[:\-]\s*(.+)$/)
      if (matched) {
        return {
          name: matched[1].trim(),
          amount: matched[2].trim(),
        }
      }
      return {
        name: line,
        amount: '',
      }
    })
}

function parseOrigins(value) {
  if (!value) {
    return null
  }
  return String(value)
    .split(/<br\s*\/?>/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const matched = line.match(/^(.+?)\s*[:\-]\s*(.+)$/)
      if (matched) {
        return {
          ingredient: matched[1].trim(),
          country: matched[2].trim(),
        }
      }
      return {
        ingredient: line,
        country: '',
      }
    })
}

main().catch(error => {
  console.error(error)
  process.exitCode = 1
})
