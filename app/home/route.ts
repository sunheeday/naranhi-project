import { NextResponse, type NextRequest } from 'next/server'

/** 개발·시연용 진입로. DEV_LOGIN_ENABLED 가 켜져 있을 때만 개발 계정으로 즉시 로그인한다.
 *  꺼져 있으면 평범한 로그인 화면으로 보낸다. 우회 스위치는 이 값 하나뿐이다. */
export async function GET(request: NextRequest) {
  if (process.env.DEV_LOGIN_ENABLED !== 'true') {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const devLoginUrl = new URL('/api/auth/dev-login', request.url)
  const upstream = await fetch(devLoginUrl, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ next: '/' }),
  })

  const payload = await upstream.json().catch(() => null)
  if (!upstream.ok || !payload?.ok) {
    const reason = payload?.error ?? 'dev_login_failed'
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(reason)}`, request.url))
  }

  const response = NextResponse.redirect(new URL(payload.next ?? '/', request.url))
  const setCookie = upstream.headers.getSetCookie?.() ?? []
  for (const cookie of setCookie) {
    response.headers.append('set-cookie', cookie)
  }
  return response
}
