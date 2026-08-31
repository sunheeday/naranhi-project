import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { appendNextParam } from './lib/auth/redirect'
import { withAuthCookieMaxAge } from './lib/supabase/config'

const PUBLIC_PATHS = [
  '/home',
  '/login',
  '/auth/callback',
  '/api/auth/dev-login',
  '/api/health',
  '/api/supabase/health',
  '/api/locale',
  // 학교(선생님) 어드민 데모: 서버 연결 없이 로컬에서 화면을 확인하기 위한 공개 경로
  '/admin',
  '/api/admin',
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
            response.cookies.set(name, value, withAuthCookieMaxAge(value, options))
          })
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'))

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
