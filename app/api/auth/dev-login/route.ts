import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import type { Database } from '@/types/database'
import { safeNextPath } from '@/lib/auth/redirect'
import { isValidLocale } from '@/lib/i18n'
import { AUTH_COOKIE_MAX_AGE_SECONDS } from '@/lib/supabase/config'

export async function POST(request: NextRequest) {
  // 프로덕션에서도 켤 수 있다(사용자 결정 2026-08-26). 스위치는 DEV_LOGIN_ENABLED 하나뿐이며,
  // 이 값을 'true' 가 아닌 것으로 바꾸면 우회 경로가 완전히 닫힌다.
  if (process.env.DEV_LOGIN_ENABLED !== 'true') {
    return NextResponse.json({ ok: false, error: 'dev_login_disabled' }, { status: 404 })
  }

  const email = process.env.DEV_LOGIN_EMAIL
  const password = process.env.DEV_LOGIN_PASSWORD
  if (!email || !password) {
    return NextResponse.json({ ok: false, error: 'dev_login_not_configured' }, { status: 503 })
  }

  const body = await request.json().catch(() => null)
  const next = safeNextPath(body?.next)
  const profileEmail = typeof body?.profileEmail === 'string' ? body.profileEmail.trim() : ''
  const displayName = typeof body?.displayName === 'string' ? body.displayName.trim() : ''
  const resetOnboarding = body?.resetOnboarding === true
  const response = NextResponse.json({ ok: true, next })

  const supabase = createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value)
            // @supabase/ssr 는 DEFAULT_COOKIE_OPTIONS.maxAge(400일)를 항상 채워서 넘기므로
            // 여기서 무조건 우리 상수로 덮어써야 한다 (lib/supabase/server.ts·middleware.ts 와 동일 패턴).
            response.cookies.set(name, value, {
              ...options,
              maxAge: AUTH_COOKIE_MAX_AGE_SECONDS,
            })
          })
        },
      },
    }
  )

  const { error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) {
    return NextResponse.json({ ok: false, error: 'dev_login_failed' }, { status: 401 })
  }

  const { data: { user } } = await supabase.auth.getUser()
  if (user) {
    if (resetOnboarding) {
      const { error: deleteChildrenError } = await supabase
        .from('children')
        .delete()
        .eq('user_id', user.id)

      if (deleteChildrenError) {
        return NextResponse.json({ ok: false, error: 'dev_login_reset_failed' }, { status: 500 })
      }
    }

    const { data: profile } = await supabase
      .from('profiles')
      .select('locale,native_language,email,display_name')
      .eq('id', user.id)
      .maybeSingle()

    const nextProfile = {
      id: user.id,
      email: profileEmail || profile?.email || user.email || null,
      display_name: displayName || profile?.display_name || null,
      locale: isValidLocale(profile?.locale) ? profile.locale : 'ko',
      native_language: isValidLocale(profile?.native_language) ? profile.native_language : 'ko',
    }

    const { error: profileUpsertError } = await supabase
      .from('profiles')
      .upsert(nextProfile, { onConflict: 'id' })

    if (profileUpsertError) {
      return NextResponse.json({ ok: false, error: 'dev_login_profile_failed' }, { status: 500 })
    }

    if (isValidLocale(nextProfile.locale)) {
      response.cookies.set('locale', nextProfile.locale, {
        path: '/',
        maxAge: 31_536_000,
        sameSite: 'lax',
      })
    }
  }

  return response
}
