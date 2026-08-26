import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { appendNextParam } from './lib/auth/redirect'
import { AUTH_COOKIE_MAX_AGE_SECONDS } from './lib/supabase/config'

const PUBLIC_PATHS = [
  '/home',
  '/login',
  '/auth/callback',
  '/api/auth/dev-login',
  '/api/health',
  '/api/supabase/health',
  '/api/locale',
]

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  let response = NextResponse.next({ request })

  const supabase = createServerClient(
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
            // options?.maxAge 는 절대 undefined 가 아니다 — `??` 로는 우리 값이 적용되지 않는다.
            response.cookies.set(name, value, {
              ...options,
              maxAge: AUTH_COOKIE_MAX_AGE_SECONDS,
            })
          })
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  if (!user && !isPublic) {
    return NextResponse.redirect(
      new URL(appendNextParam('/login', `${pathname}${request.nextUrl.search}`), request.url)
    )
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|icons|manifest.json|characters|.*\\..*).*)'],
}
