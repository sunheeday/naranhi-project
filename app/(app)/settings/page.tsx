import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { getLatestChildForUser } from '@/lib/server-cache'
import { ensureTestBypassChild, isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import BrandHeader from '@/components/brand/BrandHeader'
import CharacterImage from '@/components/brand/CharacterImage'
import LogoutButton from './LogoutButton'
import SchoolReselect from './SchoolReselect'
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

  const isPreview = await isUiPreviewEnabled()
  const testEntryBypass = isTestEntryBypassEnabled()

  if (isPreview) {
    child = {
      id: 'preview-child',
      school_name: '나란히초등학교',
      neis_school_code: 'PREVIEW',
      grade: 1,
      class_no: 1,
      dietary_restrictions: [],
    }
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = testEntryBypass
      ? { data: { user: null } }
      : await supabase.auth.getUser()
    if (!user && !testEntryBypass) redirect('/login')

    const latestChild = testEntryBypass
      ? await ensureTestBypassChild()
      : await getLatestChildForUser(user!.id)
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
  }

  const childGradeLabel = child
    ? `${child.grade}-${child.class_no ?? ''}`
    : ''

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

        <section aria-labelledby="lang-heading">
          <h2 id="lang-heading" className="text-sm font-semibold text-text-secondary mb-3">
            {messages.settings.language}
          </h2>
          <LanguageSwitcher currentLocale={locale} />
        </section>

        <hr className="border-border" />

        {child && !isPreview && !testEntryBypass && (
          <>
            <DietaryRestrictionsForm
              childId={child.id}
              initialValue={child.dietary_restrictions}
              locale={locale}
            />
            <hr className="border-border" />
          </>
        )}

        {child && !isPreview && !testEntryBypass && (
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

        {!testEntryBypass && (
        <section>
          {isPreview ? (
            <a
              href="/demo/exit"
              className="flex items-center justify-center w-full h-12 rounded-btn border border-border bg-surface text-text-primary text-base font-semibold"
            >
              데모 종료
            </a>
          ) : (
            <LogoutButton label={messages.settings.logout} />
          )}
        </section>
        )}

        <p className="text-xs text-text-disabled text-center mt-4">
          {messages.settings.version.replace('{version}', '0.1.0')}
        </p>
      </div>
    </main>
  )
}
