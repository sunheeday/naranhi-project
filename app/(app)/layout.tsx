import { cookies } from 'next/headers'
import BottomNav from '@/components/layout/BottomNav'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  return (
    <>
      {children}
      <BottomNav labels={messages.nav} />
    </>
  )
}
