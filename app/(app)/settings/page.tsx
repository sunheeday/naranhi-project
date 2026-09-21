import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServiceClient } from '@/lib/supabase/server'
import { getViewer } from '@/lib/viewer'
import { BYPASS_SCHOOLS, getSelectedBypassSchool } from '@/lib/test-entry-bypass'
import { applyBellOverrides } from '@/lib/bell-schedule'
import { ensureBellSchedule } from '@/lib/bell-schedule-store'
import BellOffsetForm from './BellOffsetForm'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import BrandHeader from '@/components/brand/BrandHeader'
import CharacterImage from '@/components/brand/CharacterImage'
import LogoutButton from './LogoutButton'
import SchoolReselect from './SchoolReselect'
import DemoSchoolPicker from './DemoSchoolPicker'
import DietaryRestrictionsForm from './DietaryRestrictionsForm'
import type { DietaryRestrictionId } from '@/lib/dietary-restrictions'

export default async function SettingsPage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  let child: {
    id: string
    school_name: string
    neis_school_code: string | null
    grade: number
    class_no: number | null
    dietary_restrictions: DietaryRestrictionId[]
  } | null = null

  const viewer = await getViewer()
  if (!viewer) redirect('/login')

  const latestChild = await viewer.latestChild()
  // 시연 방문자가 지금 고른 학교. 드롭다운의 현재 값이다.
  const selectedBypassKey = viewer.demo ? (await getSelectedBypassSchool()).key : null
  child = latestChild
    ? {
        id: latestChild.id,
        school_name: latestChild.school_name,
        neis_school_code: latestChild.neis_school_code,
        grade: latestChild.grade,
        class_no: latestChild.class_no,
        dietary_restrictions: latestChild.dietary_restrictions,
      }
    : null

  const childGradeLabel = child
    ? `${child.grade}-${child.class_no ?? ''}`
    : ''

  // 지금 이 자녀에게 적용된 1교시 시작 시각. 학교가 연결되지 않았으면 칸을 띄우지 않는다.
  let firstPeriodStart: string | null = null
  if (latestChild?.school_id) {
    const bell = applyBellOverrides(
      await ensureBellSchedule(
        createSupabaseServiceClient(),
        latestChild.school_id,
        latestChild.school_name,
      ),
      {
        offsetMinutes: latestChild.bell_offset_minutes ?? 0,
        breakMinutes: latestChild.bell_break_minutes,
        lunchMinutes: latestChild.bell_lunch_minutes,
      },
    )
    firstPeriodStart = bell[0]?.startTime ?? null
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <BrandHeader title={messages.settings.title} />

      <div className="flex flex-col gap-6 px-6 pt-6">
        {child && (
          <section
            className="flex items-center gap-4 rounded-card bg-primary-soft p-4"
            aria-label={messages.settings.school_section_title ?? '학교 정보'}
          >
            <CharacterImage character="holdingHands" size={56} disc className="shrink-0" />
            <div className="min-w-0">
              <p className="text-base font-bold text-ink truncate">{child.school_name}</p>
              <p className="text-sm text-muted mt-0.5 truncate">{childGradeLabel}</p>
            </div>
          </section>
        )}

        {viewer.demo && selectedBypassKey && (
          <>
            <DemoSchoolPicker
              schools={BYPASS_SCHOOLS.map(s => ({ key: s.key, name: s.name }))}
              currentKey={selectedBypassKey}
              title={messages.settings.demo_school_select ?? '학교 선택'}
            />
            <hr className="border-border" />
          </>
        )}

        <section aria-labelledby="lang-heading">
          <h2 id="lang-heading" className="text-sm font-semibold text-text-secondary mb-3">
            {messages.settings.language}
          </h2>
          <LanguageSwitcher currentLocale={locale} />
        </section>

        <hr className="border-border" />

        {child && (
          <>
            <DietaryRestrictionsForm
              childId={child.id}
              initialValue={child.dietary_restrictions}
              locale={locale}
            />
            <hr className="border-border" />
          </>
        )}

        {child && firstPeriodStart && (
          <>
            <BellOffsetForm
              childId={child.id}
              currentStart={firstPeriodStart}
              currentBreak={latestChild?.bell_break_minutes ?? null}
              currentLunch={latestChild?.bell_lunch_minutes ?? null}
              labels={{
                title: messages.settings.bell_title ?? '학교 시간',
                help: messages.settings.bell_help ?? '우리 학교 1교시가 몇 시에 시작하나요? 나머지 시간은 자동으로 맞춰집니다.',
                label: messages.settings.bell_label ?? '1교시 시작',
                breakLabel: messages.settings.bell_break_label ?? '쉬는 시간(분)',
                lunchLabel: messages.settings.bell_lunch_label ?? '점심시간(분)',
                blankHint: messages.settings.bell_blank_hint ?? '비워 두면 기본값을 씁니다.',
                breakRangeError: messages.settings.bell_break_range_error ?? '쉬는 시간은 0분에서 60분 사이로 넣어주세요.',
                lunchRangeError: messages.settings.bell_lunch_range_error ?? '점심시간은 0분에서 120분 사이로 넣어주세요.',
                save: messages.common.save,
                saving: messages.settings.school_saving ?? '저장 중...',
                saved: messages.settings.school_saved ?? '저장되었어요.',
                error: messages.settings.bell_error ?? '시간을 저장하지 못했어요.',
              }}
            />
            <hr className="border-border" />
          </>
        )}

        {child && !viewer.demo && (
          <>
            <SchoolReselect
              childId={child.id}
              currentSchoolName={child.school_name}
              currentGrade={child.grade}
              currentClassNo={child.class_no}
              hasNeisCode={!!child.neis_school_code}
              labels={{
                title: messages.settings.school_section_title ?? '학교 정보',
                current_label: messages.settings.school_code_set ?? '급식 정보 연동됨',
                current_unset: messages.settings.school_code_unset ?? '학교 코드 미등록 (급식 표시 안 됨)',
                reselect_button: messages.settings.school_reselect ?? '다시 선택',
                cancel: messages.common.cancel,
                save: messages.common.save,
                saving: messages.settings.school_saving ?? '저장 중...',
                saved: messages.settings.school_saved ?? '저장되었어요.',
                search_placeholder: messages.onboarding.step1_placeholder,
                no_result: messages.onboarding.step1_no_result ?? '검색 결과가 없어요.',
                searching: messages.onboarding.step1_searching ?? '검색 중...',
                search_error: messages.onboarding.step1_search_error ?? '검색 실패',
                required: messages.onboarding.step1_school_required ?? '학교를 선택해 주세요.',
                grade_label: messages.onboarding.step2_grade ?? '{grade}학년',
                class_label: messages.onboarding.step2_class ?? '{class}반',
                grade_placeholder: '학년 선택',
                class_placeholder: '반 입력',
              }}
            />
            <hr className="border-border" />
          </>
        )}

        {!viewer.demo && (
          <section>
            <LogoutButton label={messages.settings.logout} />
          </section>
        )}

        <p className="text-xs text-text-disabled text-center mt-4">
          {messages.settings.version.replace('{version}', '0.1.0')}
        </p>
      </div>
    </main>
  )
}
