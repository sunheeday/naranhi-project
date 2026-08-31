import { NextResponse, type NextRequest } from 'next/server'
import { ADMIN_COOKIE_NAME } from '@/lib/admin/cookie'
import { revokeCurrentAdminSession } from '@/lib/admin/session'

export async function POST(request: NextRequest) {
  await revokeCurrentAdminSession()
  // (protected)/layout.tsx 의 로그아웃 <form> 은 HTML 폼 제출(리다이렉트 기대),
  // 다른 호출자는 fetch(JSON 기대)일 수 있다 — Accept 헤더로 갈라준다.
  const wantsHtml = (request.headers.get('accept') ?? '').includes('text/html')
  const response = wantsHtml
    ? NextResponse.redirect(new URL('/admin/login', request.url), { status: 303 })
    : NextResponse.json({ ok: true })
  // 발급 때와 동일한 속성으로 지워야 브라우저가 같은 쿠키로 인식해 즉시 만료시킨다.
  response.cookies.set(ADMIN_COOKIE_NAME, '', {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    path: '/',
    maxAge: 0,
  })
  return response
}
