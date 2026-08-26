import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import type { Database } from '@/types/database'
import { safeNextPath } from '@/lib/auth/redirect'
import { publicOrigin } from '@/lib/request-origin'
import { AUTH_COOKIE_MAX_AGE_SECONDS } from '@/lib/supabase/config'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const origin = publicOrigin(request)
  const code = searchParams.get('code')
  const callbackError = searchParams.get('error')
  const next = safeNextPath(searchParams.get('next'))

  if (callbackError) {
    const loginUrl = new URL('/login', origin)
    loginUrl.searchParams.set('error', callbackError)
    if (next !== '/') loginUrl.searchParams.set('next', next)
    return NextResponse.redirect(loginUrl)
  }

  if (!code) {
    const loginUrl = new URL('/login', origin)
    loginUrl.searchParams.set('error', 'auth_callback_failed')
    if (next !== '/') loginUrl.searchParams.set('next', next)
    return NextResponse.redirect(loginUrl)
  }

  const response = NextResponse.redirect(`${origin}${next}`)

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

  const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
  if (exchangeError || !data?.session) {
    const loginUrl = new URL('/login', origin)
    loginUrl.searchParams.set('error', 'auth_callback_failed')
    if (next !== '/') loginUrl.searchParams.set('next', next)
    return NextResponse.redirect(loginUrl)
  }

  response.cookies.set('ui_preview', '', {
    path: '/',
    maxAge: 0,
    sameSite: 'lax',
  })

  return response
}
