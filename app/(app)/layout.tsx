import { cookies } from 'next/headers'
import BottomNav from '@/components/layout/BottomNav'
import NoticeTranslationBanner from '@/components/notice/NoticeTranslationBanner'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  return (
    <>
      {children}
      <NoticeTranslationBanner
        locale={locale}
        messages={{
          pending: messages.home.translation_pending_banner ?? '학교 공지 번역이 끝나면 알려드릴게요.',
          complete: messages.home.translation_complete_banner ?? '학교 공지 번역이 완료됐어요.',
          view: messages.home.translation_complete_action ?? '보러 가기',
          close: messages.common.close ?? '닫기',
        }}
      />
      <BottomNav labels={messages.nav} />
    </>
  )
}
