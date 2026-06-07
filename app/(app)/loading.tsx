import { cookies } from 'next/headers'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'

export default async function HomeLoading() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default
  const loading = messages.common.loading ?? 'Loading...'

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6 pb-20">
      <div className="flex flex-col items-center gap-4 rounded-[28px] bg-white/92 px-8 py-7 shadow-card backdrop-blur-[2px]">
        <LoadingSpinner size="lg" label={loading} />
        <p className="text-sm font-semibold text-muted-soft">{loading}</p>
      </div>
    </main>
  )
}
