import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import CharacterImage from '@/components/brand/CharacterImage'
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
    <main className="flex flex-col min-h-screen brand-header-bg px-6 pt-14 pb-8">
      <div className="absolute top-4 end-4">
        <LanguageSwitcher currentLocale={locale} compact />
      </div>

      <div className="flex flex-col items-center mt-10 mb-9">
        {/* 브랜드 캐릭터: 나리·누리 손 흔들기 */}
        <CharacterImage character="wave" size={168} disc priority className="mb-5" />
        <h1 className="text-3xl font-bold text-ink" style={{ letterSpacing: '-0.02em' }}>{loginMessages.title}</h1>
        <p className="text-sm text-muted mt-2 text-center">{loginMessages.subtitle}</p>
      </div>

      <section className="rounded-card border border-hairline bg-surface p-5 mb-6 shadow-soft">
        <h2 className="text-base font-semibold text-ink">{loginMessages.language_title}</h2>
        <p className="text-sm text-muted mt-1 mb-4">{loginMessages.language_body}</p>
        <LanguageSwitcher currentLocale={locale} />
      </section>

      <LoginButtons
        messages={loginMessages}
        initialError={initialError}
        nextPath={next}
        googleLoginEnabled={process.env.AUTH_GOOGLE_ENABLED !== 'false'}
        devLoginEnabled={process.env.DEV_LOGIN_ENABLED === 'true'}
      />

      <p className="text-xs text-muted-soft text-center mt-8 leading-relaxed">
        {loginMessages.terms}
      </p>
    </main>
  )
}
