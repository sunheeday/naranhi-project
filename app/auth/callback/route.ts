import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import type { Database } from '@/types/database'
import { safeNextPath } from '@/lib/auth/redirect'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const origin = _publicOrigin(request)
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
            response.cookies.set(name, value, options)
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

  return response
}

// Cloud Run에서는 request.url의 origin이 컨테이너 내부 주소(0.0.0.0:8080)로 나오므로,
// 프록시가 넘겨주는 x-forwarded-host를 우선 사용해 공개 URL을 복원한다.
function _publicOrigin(request: NextRequest): string {
  const forwardedHost = request.headers.get('x-forwarded-host')
  const host = forwardedHost ?? request.headers.get('host')
  if (!host) {
    return process.env.NEXT_PUBLIC_SITE_URL ?? new URL(request.url).origin
  }
  const forwardedProto = request.headers.get('x-forwarded-proto') ?? 'https'
  return `${forwardedProto}://${host}`
}
