const { createClient } = require('@supabase/supabase-js')

const url = 'http://127.0.0.1:54321'
const key =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU'
const supabase = createClient(url, key)

const userId = 'e8af10ac-95e0-4342-8121-e4564bff75a9'
const schoolId = 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8613001'

const notices = [
  {
    id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8613101',
    title: '2026학년도 부천부흥초 홈페이지 가입 안내',
    detailUrl: 'https://www.bucheonbuhung.es.kr/notice/3101',
    sourcePostUid: 'demo-bh-3101',
    originalText:
      '가정과 학교의 원활한 소통을 위해 부천부흥초 홈페이지에 가입해 주세요. 보호자는 2026년 6월 12일까지 회원가입을 완료하고, 학생 이름으로 학급 정보를 확인해야 합니다. 첨부된 가입 매뉴얼 PDF와 HWP를 참고해 주세요.',
    translated: {
      en: 'Please sign up for the Bucheon Buhung Elementary School website for smooth communication between home and school. Guardians should complete registration by June 12, 2026 and verify class information under the student name. Please refer to the attached sign-up guide PDF and HWP.',
      ar: 'يرجى التسجيل في موقع مدرسة بوتشيون بوهونغ الابتدائية لضمان التواصل السلس بين المنزل والمدرسة. يجب على أولياء الأمور إكمال التسجيل بحلول 12 يونيو 2026 والتحقق من معلومات الصف باسم الطالب. يُرجى الرجوع إلى دليل التسجيل المرفق بصيغتي PDF وHWP.',
      ru: 'Пожалуйста, зарегистрируйтесь на сайте начальной школы Бучхон Бухын для удобной связи между домом и школой. Родителям нужно завершить регистрацию до 12 июня 2026 года и проверить информацию о классе под именем ученика. Пожалуйста, ознакомьтесь с приложенной инструкцией в PDF и HWP.',
    },
    summaryKo: '6월 12일까지 홈페이지 회원가입을 완료하고 첨부 매뉴얼을 확인해 주세요.',
    summaryTranslations: {
      en: 'Complete website registration by June 12 and review the attached guide.',
      ar: 'أكملوا التسجيل في الموقع بحلول 12 يونيو وراجعوا الدليل المرفق.',
      ru: 'Завершите регистрацию на сайте до 12 июня и ознакомьтесь с приложенной инструкцией.',
    },
    dueDate: '2026-06-12',
    eventDates: ['2026-06-12'],
    eventLocation: null,
    cards: [
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614101',
        type: 'action',
        order: 0,
        ko: [
          { text: '홈페이지 회원가입 완료', hint: '2026-06-12' },
          { text: '학생 이름으로 학급 정보 확인' },
        ],
        translated: {
          en: [
            { text: 'Complete website registration', hint: '2026-06-12' },
            { text: 'Check class information under the student name' },
          ],
          ar: [
            { text: 'أكملوا التسجيل في الموقع', hint: '2026-06-12' },
            { text: 'تحققوا من معلومات الصف باسم الطالب' },
          ],
          ru: [
            { text: 'Завершите регистрацию на сайте', hint: '2026-06-12' },
            { text: 'Проверьте информацию о классе под именем ученика' },
          ],
        },
      },
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614102',
        type: 'supplies',
        order: 1,
        ko: [{ text: '첨부 PDF 가입 매뉴얼' }, { text: '첨부 HWP 가입 매뉴얼' }],
        translated: {
          en: [{ text: 'Attached PDF sign-up guide' }, { text: 'Attached HWP sign-up guide' }],
          ar: [{ text: 'دليل التسجيل المرفق بصيغة PDF' }, { text: 'دليل التسجيل المرفق بصيغة HWP' }],
          ru: [{ text: 'Приложенная инструкция PDF' }, { text: 'Приложенная инструкция HWP' }],
        },
      },
    ],
    attachments: [
      {
        sourceId: 'att-3101-pdf',
        filename: '홈페이지_가입_안내.pdf',
        originUrl: 'https://www.bucheonbuhung.es.kr/files/signup-guide.pdf',
        publicUrl: 'https://www.bucheonbuhung.es.kr/files/signup-guide.pdf',
        fileType: 'pdf',
        refined: '홈페이지 가입 절차와 비밀번호 설정 방법을 안내합니다.',
        translated: {
          en: 'This guide explains the website registration steps and password setup.',
          ar: 'يوضح هذا الدليل خطوات التسجيل في الموقع وكيفية إعداد كلمة المرور.',
          ru: 'Это руководство объясняет шаги регистрации на сайте и настройку пароля.',
        },
      },
      {
        sourceId: 'att-3101-hwp',
        filename: '홈페이지_가입_안내.hwp',
        originUrl: 'https://www.bucheonbuhung.es.kr/files/signup-guide.hwp',
        publicUrl: 'https://www.bucheonbuhung.es.kr/files/signup-guide.hwp',
        fileType: 'hwp',
        refined: '학부모 인증과 자녀 연결 방법을 안내합니다.',
        translated: {
          en: 'This guide explains parent verification and child linking.',
          ar: 'يوضح هذا الدليل التحقق من ولي الأمر وربط الطفل.',
          ru: 'Это руководство объясняет подтверждение родителя и привязку ребенка.',
        },
      },
    ],
  },
  {
    id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8613102',
    title: '위험 물품 및 학생 소지 금지 물품 안내',
    detailUrl: 'https://www.bucheonbuhung.es.kr/notice/3102',
    sourcePostUid: 'demo-bh-3102',
    originalText:
      '학생 안전을 위해 위험 물품과 소지 금지 물품을 학교에 가져오지 않도록 지도해 주세요. 칼, 라이터, 전자담배, 과도한 현금은 학교 반입이 금지됩니다. 가정에서 가방을 함께 점검해 주세요.',
    translated: {
      en: 'For student safety, please guide children not to bring hazardous or prohibited items to school. Knives, lighters, e-cigarettes, and excessive cash are not allowed on campus. Please check school bags together at home.',
      ar: 'من أجل سلامة الطلاب، يرجى توجيه الأطفال إلى عدم إحضار المواد الخطرة أو المحظورة إلى المدرسة. السكاكين والولاعات والسجائر الإلكترونية والمبالغ النقدية الكبيرة ممنوعة في المدرسة. يُرجى فحص الحقائب معًا في المنزل.',
      ru: 'В целях безопасности учеников, пожалуйста, объясните детям, что нельзя приносить в школу опасные или запрещенные предметы. Ножи, зажигалки, электронные сигареты и крупные суммы наличных запрещены. Пожалуйста, проверяйте школьные сумки дома вместе.',
    },
    summaryKo: '위험 물품과 소지 금지 물품을 학교에 가져오지 않도록 가정에서 가방을 점검해 주세요.',
    summaryTranslations: {
      en: 'Please check bags at home so students do not bring hazardous or prohibited items to school.',
      ar: 'يرجى فحص الحقائب في المنزل حتى لا يحضر الطلاب مواد خطرة أو محظورة إلى المدرسة.',
      ru: 'Пожалуйста, проверяйте сумки дома, чтобы ученики не приносили в школу опасные или запрещенные предметы.',
    },
    dueDate: null,
    eventDates: [],
    eventLocation: null,
    cards: [
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614201',
        type: 'action',
        order: 0,
        ko: [{ text: '가정에서 학생 가방 함께 점검하기' }],
        translated: {
          en: [{ text: "Check the student's bag together at home" }],
          ar: [{ text: 'افحصوا حقيبة الطالب معًا في المنزل' }],
          ru: [{ text: 'Проверяйте школьную сумку ребенка вместе дома' }],
        },
      },
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614202',
        type: 'supplies',
        order: 1,
        ko: [{ text: '반입 금지: 칼, 라이터, 전자담배, 과도한 현금' }],
        translated: {
          en: [{ text: 'Do not bring: knives, lighters, e-cigarettes, excessive cash' }],
          ar: [{ text: 'ممنوع الإحضار: السكاكين والولاعات والسجائر الإلكترونية والمبالغ النقدية الكبيرة' }],
          ru: [{ text: 'Запрещено приносить: ножи, зажигалки, электронные сигареты, крупные суммы наличных' }],
        },
      },
    ],
    attachments: [
      {
        sourceId: 'att-3102-pdf',
        filename: '위험_물품_안내.pdf',
        originUrl: 'https://www.bucheonbuhung.es.kr/files/safety-items.pdf',
        publicUrl: 'https://www.bucheonbuhung.es.kr/files/safety-items.pdf',
        fileType: 'pdf',
        refined: '학교 반입 금지 물품과 생활지도를 안내합니다.',
        translated: {
          en: 'This file explains prohibited items and safety guidance.',
          ar: 'يوضح هذا الملف المواد المحظورة وإرشادات السلامة.',
          ru: 'Этот файл объясняет запрещенные предметы и правила безопасности.',
        },
      },
    ],
  },
  {
    id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8613103',
    title: '2026학년도 1학년 예방접종 미완료자 접종 안내',
    detailUrl: 'https://www.bucheonbuhung.es.kr/notice/3103',
    sourcePostUid: 'demo-bh-3103',
    originalText:
      '1학년 예방접종 미완료 학생은 2026년 6월 20일까지 접종을 완료하고 확인서를 제출해 주세요. 지정 병원 또는 보건소 방문 후 예방접종 확인서를 담임교사에게 제출해야 합니다.',
    translated: {
      en: 'Students in Grade 1 who have not completed their vaccinations should finish them by June 20, 2026 and submit the confirmation form. After visiting a designated hospital or health center, please submit the vaccination confirmation to the homeroom teacher.',
      ar: 'يجب على طلاب الصف الأول الذين لم يكملوا التطعيمات إكمالها بحلول 20 يونيو 2026 وتقديم نموذج التأكيد. بعد زيارة المستشفى المعتمد أو المركز الصحي، يُرجى تسليم تأكيد التطعيم إلى معلم الصف.',
      ru: 'Ученики 1 класса, не завершившие вакцинацию, должны завершить ее до 20 июня 2026 года и подать подтверждение. После посещения назначенной больницы или поликлиники, пожалуйста, передайте справку о вакцинации классному руководителю.',
    },
    summaryKo: '6월 20일까지 예방접종을 완료하고 담임교사에게 확인서를 제출해 주세요.',
    summaryTranslations: {
      en: 'Complete vaccinations by June 20 and submit the confirmation to the homeroom teacher.',
      ar: 'أكملوا التطعيمات بحلول 20 يونيو وسلموا التأكيد إلى معلم الصف.',
      ru: 'Завершите вакцинацию до 20 июня и передайте подтверждение классному руководителю.',
    },
    dueDate: '2026-06-20',
    eventDates: ['2026-06-20'],
    eventLocation: '지정 병원 또는 보건소',
    cards: [
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614301',
        type: 'action',
        order: 0,
        ko: [
          { text: '예방접종 완료', hint: '2026-06-20' },
          { text: '예방접종 확인서 담임교사에게 제출' },
        ],
        translated: {
          en: [
            { text: 'Complete vaccinations', hint: '2026-06-20' },
            { text: 'Submit the vaccination confirmation to the homeroom teacher' },
          ],
          ar: [
            { text: 'أكملوا التطعيمات', hint: '2026-06-20' },
            { text: 'سلّموا تأكيد التطعيم إلى معلم الصف' },
          ],
          ru: [
            { text: 'Завершите вакцинацию', hint: '2026-06-20' },
            { text: 'Передайте подтверждение вакцинации классному руководителю' },
          ],
        },
      },
      {
        id: 'f5d7f9ee-b2ad-4f6d-9bc3-df7cd8614302',
        type: 'schedule',
        order: 1,
        ko: [{ text: '마감일: 2026-06-20' }, { text: '장소: 지정 병원 또는 보건소' }],
        translated: {
          en: [{ text: 'Deadline: 2026-06-20' }, { text: 'Location: designated hospital or health center' }],
          ar: [{ text: 'الموعد النهائي: 2026-06-20' }, { text: 'المكان: المستشفى المعتمد أو المركز الصحي' }],
          ru: [{ text: 'Срок: 2026-06-20' }, { text: 'Место: назначенная больница или поликлиника' }],
        },
      },
    ],
    attachments: [
      {
        sourceId: 'att-3103-hwp',
        filename: '예방접종_안내.hwp',
        originUrl: 'https://www.bucheonbuhung.es.kr/files/vaccine-guide.hwp',
        publicUrl: 'https://www.bucheonbuhung.es.kr/files/vaccine-guide.hwp',
        fileType: 'hwp',
        refined: '예방접종 대상과 제출 서류를 정리한 안내문입니다.',
        translated: {
          en: 'This attachment lists the vaccination targets and required submission documents.',
          ar: 'يسرد هذا المرفق الفئات المستهدفة بالتطعيم والمستندات المطلوبة.',
          ru: 'В этом приложении перечислены категории вакцинации и необходимые документы.',
        },
      },
    ],
  },
]

async function main() {
  await supabase.from('schools').upsert(
    {
      id: schoolId,
      name: 'Naranhi School',
      address: 'Seoul Demo Campus, 101 Story Lane',
      homepage_url: 'https://demo.naranhi.school',
      neis_office_code: 'DEMO',
      neis_school_code: 'NARANHI001',
    },
    { onConflict: 'id' },
  )

  await supabase.from('school_crawl_state').upsert(
    {
      school_id: schoolId,
      crawl_status: 'ready',
      crawl_board_url: 'https://demo.naranhi.school/notices',
      crawl_checked_at: new Date().toISOString(),
    },
    { onConflict: 'school_id' },
  )

  await supabase.from('profiles').upsert(
    {
      id: userId,
      email: 'demo.ar.parent@naranhi.local',
      display_name: 'Naranhi Demo Parent',
      locale: 'ko',
      native_language: 'ko',
    },
    { onConflict: 'id' },
  )

  await supabase.from('children').delete().eq('user_id', userId)
  await supabase.from('children').insert({
    user_id: userId,
    school_id: schoolId,
    name: '데모 학생',
    grade: 1,
    class_no: 1,
  })

  for (const notice of notices) {
    const extractedContent = {
      summary: {
        rendered: notice.summaryKo,
        translations: notice.summaryTranslations,
      },
      sources: [
        {
          source_id: `body-${notice.id}`,
          source_type: 'html_body',
          source_role: 'body_carrier',
          label: '본문',
          original_text: notice.originalText,
          refined_text: notice.originalText,
          translations: notice.translated,
          needs_file: false,
        },
        ...notice.attachments.map(attachment => ({
          source_id: attachment.sourceId,
          source_type: 'attachment',
          source_role: 'attachment',
          label: attachment.filename,
          filename: attachment.filename,
          origin_url: attachment.originUrl,
          public_url: attachment.publicUrl,
          original_text: null,
          refined_text: attachment.refined,
          translations: attachment.translated,
          needs_file: false,
          metadata: { file_type: attachment.fileType },
        })),
      ],
    }

    await supabase.from('notices').upsert(
      {
        id: notice.id,
        school_id: schoolId,
        title: notice.title,
        original_text: notice.originalText,
        source_post_uid: notice.sourcePostUid,
        detail_url: notice.detailUrl,
        crawl_result: {
          post: {
            title: notice.title,
            url: notice.detailUrl,
          },
          attachments: notice.attachments.map(attachment => ({
            filename: attachment.filename,
            url: attachment.originUrl,
            file_type: attachment.fileType,
          })),
        },
        extracted_content: extractedContent,
        status: 'done',
        due_date: notice.dueDate,
        event_dates: notice.eventDates,
        event_location: notice.eventLocation,
        source_hard_facts: {
          hard_facts: {
            dates: notice.eventDates.map(date => ({ raw: date, normalized: date, category: 'event_date' })),
            deadlines: notice.dueDate ? [{ raw: notice.dueDate, normalized: notice.dueDate }] : [],
            locations: notice.eventLocation ? [{ raw: notice.eventLocation, normalized: notice.eventLocation }] : [],
            materials: [],
            actions_required: [],
          },
        },
      },
      { onConflict: 'id' },
    )

    for (const [language, translatedText] of Object.entries(notice.translated)) {
      await supabase.from('notice_ai_translations').upsert(
        {
          notice_id: notice.id,
          target_language: language,
          source_language: 'ko',
          translated_text: translatedText,
          validation_status: 'passed',
        },
        { onConflict: 'notice_id,target_language' },
      )
    }

    for (const card of notice.cards) {
      await supabase.from('notice_cards').upsert(
        {
          id: card.id,
          notice_id: notice.id,
          type: card.type,
          order: card.order,
          content: { ko: { items: card.ko } },
        },
        { onConflict: 'id' },
      )

      for (const language of ['en', 'ar', 'ru']) {
        await supabase.from('notice_card_translations').upsert(
          {
            notice_card_id: card.id,
            target_language: language,
            translated_content: { items: card.translated[language] },
          },
          { onConflict: 'notice_card_id,target_language' },
        )
      }
    }

    for (const eventDate of notice.eventDates) {
      await supabase.from('school_events').upsert(
        {
          school_id: schoolId,
          notice_id: notice.id,
          title: notice.title,
          event_date: eventDate,
          location: notice.eventLocation,
          description: notice.summaryKo,
          source_language: 'ko',
        },
        { onConflict: 'notice_id,event_date' },
      )
    }
  }

  console.log(JSON.stringify({ ok: true, schoolId, noticeIds: notices.map(notice => notice.id) }, null, 2))
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
