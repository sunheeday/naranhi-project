import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { appendNextParam } from './lib/auth/redirect'
import { withAuthCookieMaxAge } from './lib/supabase/config'
import { ADMIN_COOKIE_NAME } from './lib/admin/cookie'

const PUBLIC_PATHS = [
  '/home',
  '/login',
  '/auth/callback',
  '/api/auth/dev-login',
  '/api/health',
  '/api/supabase/health',
  '/api/locale',
]

/** 미인증으로 통과시키는 유일한 관리자 경로. PUBLIC_PATHS 에는 넣지 않는다 —
 *  학부모 흐름의 startsWith 매칭(위 isPublic 계산)과 섞이면 실수가 생긴다. */
const ADMIN_LOGIN_PATHS = ['/admin/login', '/api/admin/login']

/** 관리자 1차 게이트. 여기서는 쿠키 «존재» 만 본다.
 *  middleware 는 Edge 런타임이라 service_role 도 node:crypto 도 쓸 수 없고,
 *  매 요청 DB 왕복도 부적절하다. 실제 세션 검증(revoked_at·expires_at·
 *  admin_users.is_active)은 app/(admin)/admin/(protected)/layout.tsx 와
 *  requireAdminSession() 을 쓰는 각 핸들러가 다시 한다(이중 방어 ②).
 *
 *  중요한 성질: 학부모 세션 쿠키(sb-…)로도, ui_preview 같은 어떤 프리뷰 쿠키로도
 *  여기를 통과할 수 없다. DEV_LOGIN_ENABLED 로 얻은 학부모 세션은 이 판정에
 *  아무 정보도 주지 않는다 — 관리자 쿠키가 없으면 그냥 없는 것이다. */
function adminGate(request: NextRequest): NextResponse {
  const pathname = request.nextUrl.pathname

  if (ADMIN_LOGIN_PATHS.includes(pathname)) {
    return NextResponse.next({ request })
  }

  if (request.cookies.get(ADMIN_COOKIE_NAME)?.value) {
    return NextResponse.next({ request })
  }

  if (pathname.startsWith('/api/admin')) {
    // 404 다. 401 이 아니다.
    //
    // 401 은 「인증하면 뭔가 있다」를 알려준다 — 관리자 API 의 «표면» 이 드러난다.
    // 어떤 엔드포인트가 존재하는지 훑을 수 있게 되고, 그건 공격자에게 지도를 주는 것이다.
    // 사업 A 의 첨부 라우트가 같은 이유로 403 대신 404 를 쓴다.
    //
    // `requireAdminSession()` 의 거절도 `notFound()` 로 매핑돼 있다. 여기만 401 이면
    // 같은 「없는 척」 정책이 한 곳에서만 새는 셈이다.
    return NextResponse.json({ error: 'not_found' }, { status: 404 })
  }

  return NextResponse.redirect(new URL('/admin/login', request.url))
}

export async function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  // ① 관리자 경로는 다른 어떤 분기보다 먼저, 학부모 흐름(아래)에 들어가기 전에 판정한다.
  //    아래는 전부 학부모 흐름(Supabase 세션 갱신·PUBLIC_PATHS)이고, 그 흐름에
  //    우회가 하나라도 생기면 관리자 표면까지 닿는다. 순서 자체가 방어다 —
  //    관리자 요청은 학부모 미들웨어 로직(Supabase 쿠키 갱신 등)을 전혀 타지 않는다.
  if (pathname.startsWith('/admin') || pathname.startsWith('/api/admin')) {
    return adminGate(request)
  }

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
