import { NextResponse, type NextRequest } from 'next/server'
import { ADMIN_COOKIE_NAME, ADMIN_SESSION_MAX_AGE_SECONDS } from '@/lib/admin/cookie'
import { createAdminSession, verifyAdminPassword, writeAdminAudit } from '@/lib/admin/session'

/** 성공·실패 모두 이 시간까지 붙잡는다. 계정 존재 여부를 소요 시간으로 유추하지 못하게. */
const FIXED_RESPONSE_MS = 700

async function holdUntil(deadline: number): Promise<void> {
  const remaining = deadline - Date.now()
  if (remaining > 0) {
    await new Promise((resolve) => setTimeout(resolve, remaining))
  }
}

export async function POST(request: NextRequest) {
  const startedAt = Date.now()
  const body = await request.json().catch(() => null)
  const username = typeof body?.username === 'string' ? body.username.trim() : ''
  const password = typeof body?.password === 'string' ? body.password : ''

  const outcome =
    username && password
      ? await verifyAdminPassword(username, password)
      : ({ status: 'invalid' } as const)

  if (outcome.status !== 'ok') {
    await holdUntil(startedAt + FIXED_RESPONSE_MS)
    // 'locked' 와 'invalid' 를 구별해 알리지 않는다 — 알리면 계정 존재가 드러난다.
    // 비밀번호는 여기서도, verifyAdminPassword 내부에서도 로그로 나가지 않는다 —
    // 남는 값은 결과 문자열(outcome.status)뿐이다.
    return NextResponse.json({ ok: false, error: 'invalid_credentials' }, { status: 401 })
  }

  const { token, expiresAt } = await createAdminSession(outcome.adminUserId)
  await writeAdminAudit(
    {
      adminUserId: outcome.adminUserId,
      username,
      displayName: outcome.displayName,
      expiresAt,
    },
    'admin_login',
    null,
  )
  await holdUntil(startedAt + FIXED_RESPONSE_MS)

  const response = NextResponse.json({ ok: true, next: '/admin' })
  // __Host- 접두 규칙: Secure + Domain 없음 + Path=/ 를 브라우저가 강제한다.
  // 셋 중 하나라도 어기면 Set-Cookie 자체가 무시되고 쿠키가 안 붙는다 — domain 을
  // 절대 지정하지 않고 path 는 반드시 '/' 로 둔다.
  // httpOnly: true — 학부모 인증 쿠키(@supabase/ssr 기본값)가 남긴 HttpOnly=false
  // 위험(사업 A)을 여기서 반복하지 않는다. 관리자 쿠키는 자바스크립트가 절대 못 읽는다.
  response.cookies.set(ADMIN_COOKIE_NAME, token, {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    path: '/',
    maxAge: ADMIN_SESSION_MAX_AGE_SECONDS,
  })
  return response
}
