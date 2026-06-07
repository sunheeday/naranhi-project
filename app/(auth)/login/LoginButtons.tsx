'use client'

import { useState } from 'react'
import { createSupabaseBrowserClient } from '@/lib/supabase/client'
import {
  detectInAppBrowser,
  openInExternalBrowser,
  type InAppBrowserDetection,
} from '@/lib/inAppBrowser'
import { safeNextPath } from '@/lib/auth/redirect'

interface LoginMessages {
  google: string
  connecting: string
  error_google: string
  inapp_warning_title: string
  inapp_warning_body: string
  inapp_open_external: string
  inapp_manual_body: string
  inapp_copy_url: string
  inapp_copied: string
}

interface Props {
  messages: LoginMessages
  /**
   * 서버에서 전달된 초기 에러 메시지 (예: auth/callback 실패 후 쿼리스트링).
   */
  initialError?: string | null
  nextPath?: string | null
  googleLoginEnabled: boolean
  devLoginEnabled: boolean
}

export default function LoginButtons({
  messages,
  initialError = null,
  nextPath = null,
  googleLoginEnabled,
  devLoginEnabled,
}: Props) {
  const [loading, setLoading] = useState<'google' | 'dev' | null>(null)
  const [error, setError] = useState<string | null>(initialError)
  const [devEmail, setDevEmail] = useState('')
  const [devName, setDevName] = useState('')
  const [inApp] = useState<InAppBrowserDetection | null>(() => {
    const detection = detectInAppBrowser()
    return detection.isInApp ? detection : null
  })
  const [copied, setCopied] = useState(false)

  function clearPreviewCookie() {
    document.cookie = 'ui_preview=; Path=/; Max-Age=0; SameSite=Lax'
  }

  async function handleGoogle() {
    if (!googleLoginEnabled) return
    clearPreviewCookie()
    // 인앱 브라우저에서 Google OAuth는 403 disallowed_useragent로 막히므로,
    // 외부 브라우저 전환이 가능하면 그쪽으로 리다이렉트한 뒤 사용자에게 재시도를 맡긴다.
    if (inApp?.canOpenExternal) {
      openInExternalBrowser(inApp, window.location.href)
      return
    }
    setLoading('google')
    setError(null)
    const supabase = createSupabaseBrowserClient()
    const callbackUrl = new URL('/auth/callback', window.location.origin)
    const safeNext = safeNextPath(nextPath)
    if (safeNext !== '/') {
      callbackUrl.searchParams.set('next', safeNext)
    }

    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: callbackUrl.toString(),
        queryParams: {
          prompt: 'select_account',
        },
      },
    })
    if (oauthError) setError(messages.error_google)
    setLoading(null)
  }

  async function handleDevLogin() {
    setLoading('dev')
    setError(null)
    const safeNext = safeNextPath(nextPath) === '/' ? '/onboarding' : safeNextPath(nextPath)
    const response = await fetch('/api/auth/dev-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        next: safeNext,
        profileEmail: devEmail,
        displayName: devName,
        resetOnboarding: true,
      }),
    })
    const body = await response.json().catch(() => null)
    setLoading(null)

    if (!response.ok || !body?.ok) {
      setError('개발용 로그인 설정을 확인해주세요.')
      return
    }

    window.location.assign(safeNext)
  }

  async function handleCopyUrl() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard 권한 거부 시 fallback — 주소창 선택이라도 가능하도록 아무것도 안 함
    }
  }

  const isLoading = loading !== null

  return (
    <div className="flex flex-col gap-3 w-full">
      {googleLoginEnabled && inApp && (
        <InAppBrowserBanner
          messages={messages}
          canOpenExternal={inApp.canOpenExternal}
          onOpenExternal={() => openInExternalBrowser(inApp, window.location.href)}
          onCopy={handleCopyUrl}
          copied={copied}
        />
      )}

      {googleLoginEnabled && (
        <button
          onClick={handleGoogle}
          disabled={isLoading}
          aria-label={messages.google}
          aria-busy={loading === 'google'}
          className="flex items-center justify-center gap-3 w-full h-[52px] rounded-btn bg-primary text-on-primary text-base font-semibold active:bg-primary-active disabled:opacity-60 transition-colors"
        >
          {loading === 'google' ? <SpinnerWhite /> : <GoogleIconOnDark />}
          {loading === 'google' ? messages.connecting : messages.google}
        </button>
      )}

      {devLoginEnabled && (
        <div className="rounded-card border border-hairline bg-surface-card p-4">
          <p className="text-sm font-semibold text-ink">개발용 온보딩 시작</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            Google 정보 대신 이메일과 이름을 직접 넣고, 학교/아이 정보 온보딩부터 다시 시작합니다.
          </p>
          <div className="mt-3 flex flex-col gap-2">
            <input
              type="email"
              value={devEmail}
              onChange={event => setDevEmail(event.target.value)}
              placeholder="이메일 (선택)"
              className="h-11 rounded-btn border border-hairline-soft bg-white px-3 text-sm text-ink outline-none placeholder:text-muted"
              disabled={isLoading}
            />
            <input
              type="text"
              value={devName}
              onChange={event => setDevName(event.target.value)}
              placeholder="보호자 이름 (선택)"
              className="h-11 rounded-btn border border-hairline-soft bg-white px-3 text-sm text-ink outline-none placeholder:text-muted"
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={handleDevLogin}
              disabled={isLoading}
              aria-busy={loading === 'dev'}
              className="flex items-center justify-center w-full h-[52px] rounded-btn bg-surface-card border border-hairline-soft text-ink text-base font-semibold active:bg-hairline disabled:opacity-60 transition-colors"
            >
              {loading === 'dev' ? '온보딩 준비 중...' : '개발용 로그인 후 온보딩 시작'}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-center mt-2" style={{ color: '#DC2626' }}>
          {error}
        </p>
      )}
    </div>
  )
}

interface BannerProps {
  messages: LoginMessages
  canOpenExternal: boolean
  onOpenExternal: () => void
  onCopy: () => void
  copied: boolean
}

function InAppBrowserBanner({ messages, canOpenExternal, onOpenExternal, onCopy, copied }: BannerProps) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"
    >
      <p className="font-semibold mb-1.5">⚠️ {messages.inapp_warning_title}</p>
      <p className="leading-relaxed">
        {canOpenExternal ? messages.inapp_warning_body : messages.inapp_manual_body}
      </p>
      <div className="flex flex-col gap-2 mt-3">
        {canOpenExternal && (
          <button
            type="button"
            onClick={onOpenExternal}
            className="w-full h-11 rounded-btn bg-amber-500 text-white font-semibold active:scale-[0.98] transition-transform"
          >
            {messages.inapp_open_external}
          </button>
        )}
        <button
          type="button"
          onClick={onCopy}
          className="w-full h-11 rounded-btn bg-white border border-amber-300 text-amber-900 font-semibold active:scale-[0.98] transition-transform"
        >
          {copied ? `✓ ${messages.inapp_copied}` : messages.inapp_copy_url}
        </button>
      </div>
    </div>
  )
}

// 검정 배경에 올라가는 단색 G 마크 (흰색)
function GoogleIconOnDark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <path
        fill="#FFFFFF"
        d="M19.6 10.23c0-.68-.06-1.36-.17-2H10v3.79h5.39a4.6 4.6 0 0 1-2 3.02v2.5h3.22c1.89-1.74 2.99-4.3 2.99-7.31zM10 20c2.7 0 4.96-.9 6.61-2.43l-3.22-2.5c-.9.6-2.04.96-3.39.96-2.6 0-4.8-1.76-5.59-4.12H1.1v2.58A10 10 0 0 0 10 20zM4.41 11.91A6.03 6.03 0 0 1 4.1 10c0-.66.11-1.3.31-1.91V5.51H1.1A10 10 0 0 0 0 10c0 1.61.39 3.14 1.1 4.49l3.31-2.58zM10 3.96c1.47 0 2.79.5 3.83 1.5l2.85-2.85A9.94 9.94 0 0 0 10 0 10 10 0 0 0 1.1 5.51L4.41 8.1C5.2 5.72 7.4 3.96 10 3.96z"
      />
    </svg>
  )
}

function SpinnerWhite() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="animate-spin">
      <circle cx="12" cy="12" r="10" stroke="#FFFFFF" strokeWidth="3" strokeOpacity="0.3"/>
      <path d="M12 2a10 10 0 0 1 10 10" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round"/>
    </svg>
  )
}
