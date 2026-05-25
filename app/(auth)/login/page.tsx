import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import LoginButtons from './LoginButtons'

interface Props {
  searchParams: Promise<{ error?: string; next?: string }>
}

interface LoginMessages {
  title: string
  subtitle: string
  language_title: string
  language_body: string
  google: string
  terms: string
  connecting: string
  error_google: string
  error_callback: string
  error_generic: string
  inapp_warning_title: string
  inapp_warning_body: string
  inapp_open_external: string
  inapp_manual_body: string
  inapp_copy_url: string
  inapp_copied: string
}

/**
 * auth/callback이나 OAuth 프로바이더에서 리다이렉트될 때 붙는 에러 코드를
 * 사용자 친화적인 번역 문구로 매핑한다. 알 수 없는 코드는 제네릭으로 fallback.
 */
function mapErrorMessage(code: string | undefined, m: LoginMessages): string | null {
  if (!code) return null
  switch (code) {
    case 'auth_callback_failed':
      return m.error_callback
    case 'access_denied':
    case 'server_error':
    case 'temporarily_unavailable':
      return m.error_generic
    default:
      return m.error_generic
  }
}

export default async function LoginPage({ searchParams }: Props) {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale

  const messages = (await import(`@/messages/${locale}.json`)).default
  const loginMessages: LoginMessages = messages.login

  const { error: errorCode, next } = await searchParams
  const initialError = mapErrorMessage(errorCode, loginMessages)

  return (
    <main className="flex flex-col min-h-screen px-6 pt-16 pb-8">
      <div className="absolute top-4 end-4">
        <LanguageSwitcher currentLocale={locale} compact />
      </div>

      <div className="flex flex-col items-center mt-16 mb-10">
        {/* 브랜드 배지: 검정 단색 원형 로고 */}
        <div
          className="w-20 h-20 rounded-2xl bg-primary flex items-center justify-center mb-5"
          aria-hidden="true"
        >
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <circle cx="14" cy="14" r="5" fill="white" />
            <circle cx="26" cy="14" r="5" fill="white" fillOpacity="0.85" />
            <rect x="7" y="22" width="12" height="10" rx="5" fill="white" />
            <rect x="21" y="22" width="12" height="10" rx="5" fill="white" fillOpacity="0.85" />
          </svg>
        </div>
        <h1 className="text-3xl font-bold text-ink" style={{ letterSpacing: '-0.02em' }}>{loginMessages.title}</h1>
        <p className="text-sm text-muted mt-2">{loginMessages.subtitle}</p>
      </div>

      <section className="rounded-card border border-hairline bg-surface-card p-5 mb-6">
        <h2 className="text-base font-semibold text-ink">{loginMessages.language_title}</h2>
        <p className="text-sm text-muted mt-1 mb-4">{loginMessages.language_body}</p>
        <LanguageSwitcher currentLocale={locale} />
      </section>

      <LoginButtons
        messages={loginMessages}
        initialError={initialError}
        nextPath={next}
        googleLoginEnabled={process.env.AUTH_GOOGLE_ENABLED !== 'false'}
        devLoginEnabled={
          process.env.NODE_ENV !== 'production' && process.env.DEV_LOGIN_ENABLED === 'true'
        }
      />

      <p className="text-xs text-muted-soft text-center mt-8 leading-relaxed">
        {loginMessages.terms}
      </p>
    </main>
  )
}
