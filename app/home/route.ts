import { NextResponse, type NextRequest } from 'next/server'
import { publicOrigin } from '@/lib/request-origin'
import { safeNextPath } from '@/lib/auth/redirect'

/** 개발·시연용 진입로. DEV_LOGIN_ENABLED 가 켜져 있을 때만 개발 계정으로 즉시 로그인한다.
 *  꺼져 있으면 평범한 로그인 화면으로 보낸다. 우회 스위치는 이 값 하나뿐이다.
 *
 *  origin 은 반드시 publicOrigin() 으로 얻는다. Cloud Run 에서는 request.url 의 origin 이
 *  컨테이너 내부 주소(0.0.0.0:8080)로 나와서, 그걸 Location 에 넣으면 브라우저가
 *  따라갈 수 없다. app/auth/callback/route.ts 가 같은 이유로 같은 함수를 쓴다. */
export async function GET(request: NextRequest) {
  const origin = publicOrigin(request)

  if (process.env.DEV_LOGIN_ENABLED !== 'true') {
    return NextResponse.redirect(new URL('/login', origin))
  }

  const failure = (reason: string) =>
    NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(reason)}`, origin))

  // 내부 요청은 같은 컨테이너에만 닿으면 되므로 헤더에서 떼어낸다.
  // publicOrigin() 은 x-forwarded-host 를 검증 없이 신뢰하는데, 그것을 fetch 목적지로
  // 쓰면 헤더 조작으로 서버가 임의 호스트에 요청을 보내게 된다(SSRF).
  // 리다이렉트는 브라우저가 갈 주소라 publicOrigin 이 맞지만, 내부 호출은 아니다.
  const internalOrigin = `http://127.0.0.1:${process.env.PORT ?? 3000}`

  let upstream: Response
  try {
    upstream = await fetch(new URL('/api/auth/dev-login', internalOrigin), {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ next: '/' }),
    })
  } catch {
    // 내부 요청이 네트워크 레벨에서 실패해도 500 을 띄우지 않고 로그인 화면으로 보낸다.
    return failure('dev_login_unreachable')
  }

  const payload = await upstream.json().catch(() => null)
  if (!upstream.ok || !payload?.ok) {
    return failure(payload?.error ?? 'dev_login_failed')
  }

  const response = NextResponse.redirect(new URL(safeNextPath(payload.next), origin))
  for (const cookie of upstream.headers.getSetCookie?.() ?? []) {
    response.headers.append('set-cookie', cookie)
  }
  return response
}
