import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import LogoutButton from './LogoutButton'
import SchoolReselect from './SchoolReselect'

export default async function SettingsPage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  let child: { id: string; school_name: string; neis_school_code: string | null } | null = null

  if (isUiPreviewEnabled()) {
    child = {
      id: 'preview-child',
      school_name: '나란히초등학교',
      neis_school_code: 'PREVIEW',
    }
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) redirect('/login')

    const result = await supabase
      .from('children')
      .select('id, school_name, neis_school_code')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()

    child = result.data
  }

  return (
    <main className="flex flex-col min-h-screen pb-20">
      <header className="sticky top-0 bg-surface border-b border-border px-6 py-4 z-10">
        <h1 className="text-lg font-bold text-text-primary">{messages.settings.title}</h1>
      </header>

      <div className="flex flex-col gap-6 px-6 pt-6">
        <section aria-labelledby="lang-heading">
          <h2 id="lang-heading" className="text-sm font-semibold text-text-secondary mb-3">
            {messages.settings.language}
          </h2>
          <LanguageSwitcher currentLocale={locale} />
        </section>

        <hr className="border-border" />

        {child && !isUiPreviewEnabled() && (
          <>
            <SchoolReselect
              childId={child.id}
              currentSchoolName={child.school_name}
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
              }}
            />
            <hr className="border-border" />
          </>
        )}

        <section>
          <LogoutButton label={messages.settings.logout} />
        </section>

        <p className="text-xs text-text-disabled text-center mt-4">
          {messages.settings.version.replace('{version}', '0.1.0')}
        </p>
      </div>
    </main>
  )
}
